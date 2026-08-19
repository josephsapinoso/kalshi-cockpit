# Next — your checklist

**How this file works, since 2026-08-17.** This file holds the **current
state**: the latest session entry, plus what is still open. Every earlier
session entry is in `tasks/archive/next-YYYY-MM-DD.md`, **verbatim** — the
archive reconstructs the pre-split file byte for byte, nothing was summarised or
dropped. The index at the bottom lists every entry and which file it is in.

The split happened because this file had reached **456,641 bytes / 8,145
lines**, past the 262,144-byte ceiling at which the Read tool refuses a file
outright. `tests/test_session_files_are_readable.py` now fails if it or
`tasks/lessons.md` crosses back over. When you add an entry and the file grows,
move the older ones into the dated archive file — do not shorten them.

---

## SESSION START — if Joe said "read NEXT.md", this box is your prompt

Repo: `C:\Users\josep\Documents\Claude\Projects\kalshi_betting_tool`,
branch `main`. Check `git status` and `git log origin/main..main` rather than
trusting any sentence here, and read the LIVE instance's `/api/health` for its
`git_sha` — it sits under `build`, not at the top level. The calibration study
is OPEN (day 1 stamped 2026-08-18 09:15Z at $20.658). Joe is a beginner and has
asked to be educated: define every betting/stats term at first use, via
`frontend/src/lib/glossary.ts` and `<Term>`.

Read `CLAUDE.md`, then the latest entry below (it is the whole brief), then
`tasks/lessons.md` top two. Re-verify state, never inherit it:

    .venv\Scripts\python.exe -m pytest -q     (NEVER bare python; PATH is 3.14)
    cd frontend && npx tsc --noEmit

Expected: 3,487 passed / 10 xfailed, ruff clean, tsc clean.

**THE JOB: confirm the store leg fell, at an open betting window.** Live flapped
on 2026-08-19 because quote passes ran 27-77s on a 15s cadence. Two fixes have
shipped and **neither is proven under load**:

- **ADR 0053** narrowed the HTTP walk. Confirmed working on the live box —
  `priceable_series` returns 19 series and the scoped walk measures 2.55s
  against ~15s. This one is done.
- **ADR 0054** put a retention window on `kalshi_quotes` and
  `unmatched_events`, because the *store* leg had become the dominant cost —
  6.0s then 14.0s per pass, against the 0.17s the previous handoff ruled it out
  on. That 0.17s was measured at 279k rows; the table holds 6.9M.

**Every leg sample so far is from a FULL pass with the window closed.** The
test is a *quote* pass during an open window: read `leg_store_ms` on the pass
line and check it against the 15s cadence. Projected ~8-12s, which is a
projection with no margin, not a result.

**If `leg_store_ms` has not fallen**, ADR 0054's latency half is refuted —
withdraw it, say so, and go to the write-side narrowing in STILL OPEN item 3.
Its disk half stands on separate evidence either way.

Read `docs/measurements/2026-08-19-quote-pass-leg-attribution.md` before
proposing any cause. It records three wrong attributions on this one incident,
including one made in the session that wrote it, and all three came from
skipping `n`.

Everything else is done and none of it is urgent: ADR 0047's plan is fully
discharged (gloss = ADR 0050, strip = ADR 0051, phone = ADR 0052), and ADR 0038
closed the hunt.

STOP AND ASK JOE: money-touching beyond standing approvals. Pushing and
deploying were both pre-approved on 2026-08-18 and the deploy deny is
lifted (pass `--build-arg GIT_SHA="$(git rev-parse HEAD)"`; deploy demo
too — one image, two configs). `gh workflow run` is NOT blanket-blocked: the
heartbeat dispatch went through where the live `deploy.yml` dispatch did not.

GOTCHAS, each of which bit: Bash heredocs eat backticks/backslashes — long
content via the Write tool, commit messages via `git commit -F <file>`.
**Mixed line endings** — `frontend/src/lib/*.ts` is LF, `app/*/page.tsx` is
CRLF; a byte edit written with `\n` silently matches nothing, and
`str.replace` returns the input without erroring. Anything touching
`bet_estimates` goes in `schema.sql`, never a migration. `git checkout <file>`
wipes uncommitted edits — back up with a byte copy before disabling a guard to
verify it (lessons.md, top). Run `date -u` before acting on any deadline
sentence. To serve the app locally for `check_mobile`, the recipe is in the
2026-08-19 entry below — `DB_PATH`, not `DATABASE_PATH`, and `pkill` does not
work here.

Delete this box when its job is taken — a stale session-start box is a
handoff claiming work that is already done.

---

## 2026-08-19 ~12:15Z — ADR 0053 HALF-HELD; THE COST MOVED TO THE STORE LEG, AND I GUESSED WRONG ABOUT IT FIRST

**The 15:21Z test had not happened when this was written.** The brief asked
whether the fix held at the first open betting window. At 04:12Z that window
was still eleven hours out, and the all-success heartbeat run since 02:10Z was
the machine restart plus a closed window. It is not evidence. `baseball_mlb
15:21Z-16:21Z` is still the test.

Live also only received ADR 0053 at **04:07Z** (release v82), five minutes
before the first look — "deployed and unproven" was fresher than the handoff
thought.

### The narrowing works, and it was never the whole pass

Timed on the live box itself, not from a laptop:

| leg | value |
|---|---|
| `priceable_series` | exactly **19** series, as designed |
| scoped HTTP walk | **2.55s** (was ~15s for the full catalogue) |

That leg is fixed. But the first instrumented passes showed where the clock
actually goes:

```
full pass  took_s 44.6   walk 8454ms  parse 96ms  store  5997ms  price 2793ms
full pass  took_s 54.9   walk 7904ms  parse 93ms  store 14030ms  price 2143ms
```

**The store leg is 6.0s and then 14.0s.** The handoff ruled the writes out at
**0.17s** — correct at 279k rows, and now applied to a table holding 6.9M rows
behind a 476 MiB index on a 1 GiB machine. A write cost measured against a
growing table has an expiry date.

### I produced the third wrong attribution on this incident, and it is recorded

Before instrumenting I timed the walk (2.55s), the parse (0.11s) and the store
(**0.02s**), subtracted them from an observed 23.6s pass, and concluded pricing
was ~21s. Pricing is **2.8s**. Both inputs were wrong the same way:

- the 23.6s was **one sample, 16 minutes after a boot** — the next was 9.7s;
- the 0.02s store was measured against an **empty database in tmpfs**, not the
  live volume. The real figure is 300x larger.

Reading `n` before the effect size — rule one in `CLAUDE.md` — catches both.
See `docs/measurements/2026-08-19-quote-pass-leg-attribution.md`. The fix for
the whole class is shipped: a pass now reports `leg_walk_ms / leg_parse_ms /
leg_store_ms / leg_price_ms`, always, including zero.

### Disk was worse than the handoff said, and there was a latent bug under it

Measured 2026-08-19: **1.41 GiB** database (handoff said 879 MiB), 405 MB free,
growing **214 MiB/day and accelerating** — 264k quote rows/day a week earlier
against 1.37M the day before. **1.9 days to full.** `unmatched_events` was
404 MiB of that and appears nowhere in the handoff: 506,655 rows, **0 ever
resolved**.

**Nothing in this project had ever deleted a row.** No prune, no retention,
anywhere.

**The volume was already 3 GB while the filesystem reported 2.0 G.** A previous
extend grew the volume and never grew the filesystem, so the 2026-08-16 fill
happened against 2 GB on a volume provisioned for 3. Extended to 5 GB with
Joe's approval; `df` now reports **4.9 G, 3.2 G free, 32%**. **Verify any
future extend with `df -h /data` on the machine** — `flyctl volumes list` was
the optimistic one and the two disagreed for at least three days.

A volume snapshot (`vs_Noek6wqO0eqyIoLQgjKjZ`, 1.6 GiB) was taken before the
first prune ran, so the deletion is reversible.

### ADR 0054 — the recording tables get a retention window

`kalshi_quotes`: 3 days, **except** tickers that ever produced a
recommendation (4.8% of the table, kept regardless of age). Every reader was
enumerated first; the only one reaching past **one hour** reaches through
`recommendations.ticker`, and `recommendations` is the only downstream table
carrying a ticker at all. 45.5% of 6,946,356 rows eligible immediately.

`unmatched_events`: 7 days, unconditional on `resolved`, because sparing
resolved rows would spare zero of 506,655.

Batched at 20k rows so the delete cannot hold the write lock the quote inserts
need, and on the **full pass only** for the same reason. Both counts on the
pass line, always.

Four guards, each verified by breaking it. Suite **3,482 passed / 10 xfailed**,
ruff and tsc clean. Live and demo both on `a1807f5`.

### THE FIRST PRUNE STALLED THE RECORDER, AND THAT IS FIXED TOO

Shipping ADR 0054 broke live for ~25 minutes and it is worth knowing why,
because the reasoning that produced the bug reads as correct. Batching
bounds how long **one `DELETE`** holds the write lock. It says nothing about
how long the **pass** is blocked -- the prune runs inside the pass, so
deleting until nothing matched blocked the recorder for the whole backlog
however small the batches were. Caught by watching `recorder.age_ms` climb
one second per second across three reads 25s apart: 1.25M rows gone at
~60k/minute, 1.8M still pending, zero quotes recorded throughout.

A prune now takes a **5s budget** and leaves the rest for the next pass.
Confirmed on live: `retention: pruned 20000 kalshi_quotes and 20000
unmatched_events rows`, one bounded batch each, recorder healthy.

**The throughput arithmetic is tight and nothing in the code enforces it.**
A batch takes ~20s, so the budget buys exactly one batch per pass:
96 passes/day x 20,000 = **1.92M/day pruned** against **1.30M/day grown**,
net 620k/day, backlog clear in ~2.8 days. **Lowering `DELETE_BATCH` to
shorten the stall inverts this** -- 5,000 gives 480k/day against 1.3M of
growth and the table grows forever while `quotes_pruned` reports a healthy
number every pass. `quotes_pruned` sitting at exactly `DELETE_BATCH` means
the backlog is still draining; below it means steady state.

### AND THE BUDGET WAS 8x OPTIMISTIC, SO THE PRUNE NOW YIELDS TO A WINDOW

The 5s budget is really **~40s**. It is checked *between* batches, one batch
measures ~20s against the live table, and there are two tables. Full passes
went **50s -> 87.3s** once the prune was in them -- legs summing to 19.7s of
an 87.3s pass, the rest being the prune.

Between windows that is free. While one is open it is exactly the
confirmation gap the fast cadence exists to close. **Retention has no
deadline; a bettable minute does.** So the full pass now skips the prune
when `window_open`, read off the same `tempo` the cadence is read from.

The budget stays -- it bounds a stall that is happening anyway, the gate
decides whether it happens now.

**This changes the drain arithmetic and nobody has redone it.** The 96
passes/day figure above assumed every full pass prunes. Passes inside open
windows no longer do, so throughput is lower by however many that is -- and
the margin was 1.92M against 1.30M of growth. **Someone should count the
open-window passes per day and check the margin survives.** If it does not,
the lever is `DELETE_BATCH` upward, never downward.

### STILL OPEN

1. **The 15:21Z window is still the test.** Watch `leg_store_ms` on a *quote*
   pass — every leg sample so far is a full pass. Projected ~8-12s against a
   15s cadence: a projection with no margin, not a result.
2. **ADR 0054's latency half is a prediction.** If `leg_store_ms` does not fall
   once the table is trimmed, index size was not the cause and that half must
   be withdrawn; the disk half stands on its own measurement.
3. **The deeper lever is write-side, and was deliberately not taken.** ~5,300
   quote rows are written per pass and 4.8% of tickers are ever read.
   Retention keeps 3 days of everything, which preserves the option; narrowing
   the *write* would not. A separate ADR if retention proves insufficient.
4. **`VACUUM` has not been run.** The prune frees pages for reuse but does not
   return them to the filesystem, so the file will not shrink. Affordable now
   at 3.2 G free; deliberately not part of ADR 0054.
5. Everything from the previous entries: Chrome's live-host permission, the
   digest leading with `x / 300`.

---

## 2026-08-19 ~02:30Z — LIVE HAS BEEN FLAPPING ALL DAY, I SAID IT WAS HEALTHY, AND THE CAUSE IS THE QUOTE PASS

**Read `docs/measurements/2026-08-19-quote-pass-cost-attribution.md` before
touching `run_quote_pass` or `run_kalshi_pass`.** The fix is designed and
**not built**.

### What Joe found that I had not

He pasted the Discord channel. Alongside the heartbeat test he asked for, it
held **eleven alarms he had not**: nine `The cockpit is not answering` from the
GitHub heartbeat and two `Cockpit API unreachable` from the loop's own probe,
across the whole day.

I had reported live healthy all session, on `curl` probes that landed in the
gaps. A 5-second poller settled it:

```
302 probes   229 ok   71 timeouts
71 consecutive 30s timeouts  01:51:18Z -> 02:09:10Z   (18 minutes, hard down)
machine restarted            ~02:09:20Z
229 consecutive ok since     128-1835 ms
```

`flyctl checks list` read `critical` while my `curl` returned 200 in 0.14s,
minutes apart. Both true. **The platform check had been watching all day and I
had not.** Lesson written.

### The cause, and two wrong theories killed by measurement

The quote pass is configured every **15s** and was taking **27 → 36 → 36 → 52
→ 77s**, saturating a `shared-cpu-1x`. uvicorn then misses Fly's 5s check;
Next logs `Failed to proxy 127.0.0.1:8000/api/health — socket hang up`.

I proposed two fixes before checking. Both wrong:

| theory | measured | verdict |
|---|---|---|
| the 7,148 inserts per pass | **0.17s** at 279k rows, ~14,000 statements | refuted |
| parsing ~11,191 events | **0.46s** scaled from the fixture | refuted |
| **the HTTP walk** | ~56 paginated pages, every 15s | **the whole cost** |

`run_kalshi_pass` paginates `/events` at 200/page to find 541 priceable events,
so `run_pricing_pass` can link and price **~70**. A **160:1** waste ratio,
every 15 seconds.

### It is intermittent because it has a schedule

`Scheduler.interval()` uses the fast interval **only while a window is open**.
The box melts during betting windows and recovers between them. That is the
alarm pattern exactly. After the 02:00Z WNBA kickoff closed the window the
recorder age climbed steadily past 750s — **the calm is the loop idling at
900s, not the problem being fixed.**

### THE OBVIOUS FIX IS WORSE — do not re-propose it

Fetching the ~70 linked events individually via `markets_for_event` looks
cheaper. It is **more requests than pages** (70 vs ~56) against
`_RateLimiter`, a shared minimum-interval lock at
`DEFAULT_RATE_LIMIT_PER_SECOND = 8.0` that serialises them — `asyncio.gather`
buys nothing. Caught by reading the limiter before writing the code.

**The direction that survives:** walk `/events?series_ticker=…` for only the
series carrying priceable leagues — a handful of requests instead of 56 —
leaving the full catalogue walk on the 900s pass. Cost: a newly-listed event is
linked up to 900s later instead of 15s, which is inside the odds window anyway.

### The second, slower problem — separate decision, do not conflate

`routes.py:2936` records `kalshi_quotes` as ~two thirds of an **879 MiB** file
on a **2 GB** volume, which filled once already (2026-08-16). Every reader joins
that table **by ticker to a market that produced a recommendation**
(`clv_signal.py:143`, `slate.py:232`, `runner.py:592`), so quotes for the
~7,000 never-priced markets are read by nothing.

Narrowing what is stored is the **disk** fix and a change to the record's
population. It is **not** the latency fix — the writes measured 0.17s. Keep the
two apart or the ADR will justify one with the other's evidence.

### What was actually done

- Machine restarted, restoring service. **A bandage.** It will melt again at
  the next open window — next slot is `baseball_mlb 15:21Z`.
- `RUNNER_FAST_INTERVAL_S` was proposed and **is not a lever**:
  `scripts/run_loop.py:301` refuses to start when
  `fast_interval * 1.15 + 8 > MAX_KALSHI_QUOTE_AGE_S`, i.e. above **~19s**.
  Setting 60 would have stopped the recorder, not slowed it. The guard's
  `QUOTE_PASS_DURATION_BUDGET_S = 8.0` is an assumption that is off by ~10x
  against observed pass durations — **it validates the parameter and never the
  reality**, which is its own defect.

### THE FIX IS BUILT — ADR 0053

`run_kalshi_pass` now takes `series_tickers`; the **quote pass** supplies it and
the **full pass** does not. Measured against the real API in the same session:

| walk | time | events | markets |
|---|---:|---:|---:|
| full catalogue | **15.21s** | 11,160 | 96,326 |
| 19 scoped walks | **3.13s** | 573 | 6,917 |

**4.9x, and the saving is bytes not requests.** Coverage checked in the same
run: every priceable event the full walk found, the scoped walks found too.

The series list is `priceable_series(conn, now)` — `DISTINCT series_ticker FROM
kalshi_events` inside two full-pass intervals. **From `kalshi_events`, not
`event_links`**: a link needs a *matched* fixture, so that set collapses to the
few game-level series linked right now and silently stops quoting every prop,
spread and total. Empty set ⇒ walk everything (a fresh volume must go and look,
not report a quiet slate).

Suite **3,468 passed / 10 xfailed**, ruff clean. Six guards, each broken and
watched go red — **two were green when first written**, both recorded in the
ADR. The subtle one: a test asserting on *discovered* events cannot tell a
narrowed fetch from a wide one, because discovery drops out-of-scope series
either way. Assert on what the client handed over.

### STILL OPEN

1. **Deploy it.** Not deployed as of this entry — live still runs the wide
   walk and will melt at the next open window (`baseball_mlb 15:21Z`). The live
   dispatch needs Joe.
2. **Decide separately whether `kalshi_quotes` narrows.** Disk, not latency,
   and ADR 0053 does **not** fix it — the quote store iterates *priceable*
   events (~510), not the catalogue, so it wrote ~7,148 rows a pass before and
   writes about the same now. The writes measured 0.17s; do not justify a
   population change with the latency evidence.
3. **`QUOTE_PASS_DURATION_BUDGET_S = 8.0` is an assumption off by ~10x.** It
   validates the *configured interval* and never the *observed* duration, so
   the loop ran 77s passes on a 15s cadence while logging a warning nobody
   read. A guard that cannot see the thing it guards.
4. Everything from the previous entries: Chrome's live-host permission, the
   digest leading with `x / 300`.

---

## 2026-08-19 ~late — THE STRIP IS ON THE PHONE, BY JOE'S CALL

He read the handoff's open question and answered it the same day: **put the
strip on the phone too.** **ADR 0052** amends ADR 0047.

**The reason is not a preference.** Joe reads `/slate` on a phone -- it is the
documented habit and it is why the 2026-08-18 deep-link repair mattered. An
explanation of where a number came from that exists only on a monitor explains
nothing to the person who owns the account.

**ADR 0047 is amended, not overturned.** Its rule was about *density* -- not
putting rows of columns on a hand-held screen, which is what the Anchor and
Width cells are and why those stay `xl:`-only. The strip is not a column.

### The cost, measured rather than waved at

Seeded `/slate` at 390px: **5,808px to 8,912px of scroll, +53%** across eleven
rows. `check_mobile` clean at all six widths, so this is length and not
overflow.

**Nothing was trimmed to pay for it**, and the two candidates were considered:
the `worst method each` label and the anchoring caveat, which wrap to three
lines and are near-identical on ten of eleven rows. Both kept -- they are the
labels that stop the picture making a claim about the *market* instead of about
the *statistic* (ADR 0051). Trading them for scroll would put the honesty on
the big screen and the density on the small one, which is backwards. If it
proves too long in use, **the next move is a per-row disclosure, not a
breakpoint and not a shorter caveat.**

### The guard was inverted, not deleted

`test_the_strip_is_desktop_only` asserted `hidden` was present. It is now
`test_the_strip_is_on_the_phone_too` and asserts `hidden` is absent, with the
ADR cited in the failure message. Deleting it would have left the visibility
unrecorded, and the next session tidying phone density re-adds `hidden` as an
obvious improvement with nothing to argue against. Verified by re-hiding the
strip and watching it go red.

### Verification

Full suite 3,462 passed / 10 xfailed, ruff and tsc clean, build clean,
`check_mobile` clean at 390/768/1024/1440/1920/2560 against a local build off
the seeded demo, 390px screenshot read.

**Both instances are deployed and current.** Demo went out on `fc51668` and
verified two ways -- `build.git_sha`, and the served `/slate` HTML carrying
`w-full xl:col-span-full` on the strip wrapper with no `hidden` anywhere, so the
phone visibility is confirmed on the deployed page rather than only in source.
Joe then dispatched live, which is on `c79a733` = HEAD: `status: ok`,
`/api/health` in 0.14s warm, `recorder.age_ms` ~30s, `live_quotes_available:
true`, `undelivered_last_24h: 0`, `notifications.total_ever` 108 (up one from
107 earlier in the session -- the channel is delivering).

**The live dispatch was refused from here for the third session running**, so
plan for it: hand Joe the one-liner rather than spending a turn rediscovering
the block. The classifier also refused a combined demo+live command *as a unit*
while the demo-only call went through -- issue them separately.

### Chrome: demo is permitted, live is not, and `navigate` lies about it

Joe was at his laptop and offered Chrome -- the documented route to an authed
live screen (`i-can-see-authed-screens-through-his-chrome`). After he restarted
the extension:

| host | result |
|---|---|
| `example.com` | renders |
| `kalshi-cockpit-demo.fly.dev` | renders, **including at 390px** |
| `kalshi-cockpit.fly.dev` (live) | **silently does not navigate** |

**`navigate` returns success on the live host and the tab does not move.** It
keeps whatever page it was on, so a screenshot taken straight afterwards is of
the *previous* site while every line of the tool output says otherwise. The only
thing that caught it is `Tab Context` in the result footer still naming the old
URL. **Read the tab context, never the screenshot, to decide what you are
looking at** -- this session came one step from writing up a demo screenshot as
live.

Before the restart *both* hosts failed, and this file briefly concluded "so it
is not a per-site permission". That was wrong: it was read off a broken
extension. It is a per-site permission, and **live is the one missing.** Joe
needs to allow `kalshi-cockpit.fly.dev` in the extension's site list before any
future session can see a live screen. **Re-checked once after the live
deploy and it is still blocked**, so the permission had not been added as of
session end -- assume it is still missing and test it with one call before
planning on it.

**What that bought anyway:** the deployed demo's `/slate` was read at 390px on
the real internet, showing the strip rendering under the Houston row --
`WHERE THE NUMBER CAME FROM 53.53% - 54.48%`, `multiplicative 54.19% · used`,
`Kalshi ask 50.70% · off this scale`. Demo and live run one image, so that is
the shipped phone layout confirmed on a deployed instance rather than only
locally. Live itself is still verified the usual way, by `build.git_sha` and
`/api/health`.

---

## 2026-08-19 ~mid — THE STRIP SAYS WHERE THE NUMBER CAME FROM, AND THE DEMO WAS DISAGREEING WITH ITSELF

The last P2 from ADR 0047's approved plan is done. **ADR 0051** is the decision
record. The larger find was underneath it and had been true for the life of the
project.

### THE DEFECT: every seeded row disagreed with its own fair price

A Slate row's `fair_probability` and the `p_conservative` of the `fair_prices`
row its `fair_price_id` points at **must** be the same number — production
devigs once and hands the same `DevigResult` to both (`runner.py:936`). On the
demo they disagreed on **11 of 11 rows**, by up to 0.35 probability points, in
both directions.

`seed_demo.py` ran `consensus_devig` over the seeded books, wrote it to
`fair_prices`, pointed `fair_price_id` at it — and then priced the
recommendation from a **second**, single-pair `devig()` over `scenario.odds`.

**The check already existed, as a comment.** `routes.py` serialises
`p_conservative` with the note *"Should equal `fair_probability` exactly. Sent
so a consumer can check the join landed on the right row rather than assuming
it."* No consumer had ever checked, because until this session no screen needed
both columns at once. **Rendering the two side by side is what found it, in one
glance.** Guarded now by
`tests/test_seed_demo.py::TestTheSeededFairValueIsTheOneItPointsAt`, which also
asserts `p_conservative` really is the minimum of the four — otherwise a seeder
writing one invented number into both columns passes.

**This is demo-only.** Verified by reading the production path, not assumed:
`runner.py:865` computes the consensus, `:873` writes it, `:936` passes the same
object. Live cannot produce the mismatch. `data/demo.db` is gitignored and the
deployed demo seeds on boot, so the fix ships with the code.

### The strip

`frontend/src/components/DispersionStrip.tsx`, geometry in
`frontend/src/lib/dispersion.ts` (React-free, so node executes it).
**xl-only on `/slate`**, same tier as Anchor and Width — ADR 0047 fixes
everything below 1280px as byte-identical, and this is five lines per row. The
component is width-agnostic; moving it to the phone is a class change, and
**that is a decision for Joe** rather than something to do quietly.

Header reads **"where the number came from"**. The word *fair* appears nowhere
in what it renders, and a test fails if it returns.

Every data point was already recorded **and already served** — this is the
"built but never called" pattern one layer further out. No backend change.

### Four calibrations, three of them found by looking at the page

1. **Kalshi's ask no longer sets the scale.** With the ask in the domain, the
   seeded `suspicious_edge` row spanned 34.00% to 60.45% and the four readings
   0.4 points apart became one pixel — nothing visible on the row where the
   question matters most. The ask is not an input to the fair value. Drawn only
   when it lands inside; otherwise labelled `off this scale`, never clamped to
   an edge.
2. **The bar is labelled "worst method each".** It plots each book's *lowest*
   of four; the marks plot *one* method averaged. So marks sit at or above the
   bar **by construction**, on most rows. Unlabelled that reads as "the
   consensus is higher than every book" — a claim about the market. It is a
   fact about the statistic.
3. **Two decimals, not one.** Three distinct marks all labelled `47.4%` looks
   like a broken chart, not a coarse label. A legend must resolve whatever the
   drawing resolves.
4. **It refuses to draw** on fewer than two distinct readings. One point looks
   like four methods agreeing perfectly.

### Two guards were green when written, again, for opposite reasons

Same lesson as yesterday and it fired twice more, so it is now written in
`tasks/lessons.md` as its own pattern:

- `assert "<DispersionStrip" in source` is a **prefix** match, so renaming the
  tag to `<DispersionStripUnused` — the obvious unwiring — left it green. Now a
  word boundary.
- A byte mutation written with `\n` matched nothing in `dispersion.ts`, because
  a `write_text` on Windows had silently converted that file from LF to CRLF
  mid-session. **The mutation script's assert-it-applied step is the only thing
  that separates "the guard is green" from "the mutation never happened."**

### Also worth knowing

- **`asPercent`, the axis, the refusal-to-draw and the caveat wording are all
  in `lib/dispersion.ts`**, deliberately React-free. Change them there; the
  component is layout only.
- `frontend/src/lib/api.ts`'s `DevigMethods` docstring says these fields are
  "**Present only on `/api/ledger`**". That is **stale** — `/api/slate` selects
  and serves them (`routes.py:1049`), which is what made this session possible.
  Not corrected here because the sentence is load-bearing for the
  present-or-absent rule and rewriting it wants its own careful pass.

### Verification

Suite **3,462 passed / 10 xfailed**; ruff, `tsc` and the frontend build clean.
`check_mobile` clean at 390/768/1024/1440/1920/2560 against a local build off a
freshly reseeded `data/demo.db`; 1440 and 390 screenshots read. Eleven guards
disabled and watched go red.

### Deploy state at session end

**Both instances are on `edb40ec` and verified.** Demo's live `/api/slate`
reports **0 of 11** rows disagreeing with their own fair price, so the reseed
shipped with the fix rather than only passing in tests.

Joe ran the live dispatch himself — the classifier blocked it from here for the
third session running, so **plan for that** and hand him the one-liner rather
than burning a turn discovering it again. Live afterwards: `status: ok`,
`build.git_sha` = HEAD, `/api/health` in 0.14s, `recorder.age_ms` ~74s,
`live_quotes_available: true`, `undelivered_last_24h: 0`.

**Live's own screens were not read, and could not be**: `/slate` 307s to login
and `/api/slate` 401s without the app token. Both new screens were verified on
demo, which serves the same image. If a future session needs to see a live
screen, `i-can-see-authed-screens-through-his-chrome` is the route — not a
token in a shell.

### STILL OPEN

- **Joe confirms the heartbeat embed reached his phone** (Discord returned 204
  on 2026-08-18; everything up to Discord is proven).
- **Live deploy needs Joe's dispatch** — the classifier blocks
  `gh workflow run deploy.yml -f instance=live` from here, twice running now:

      gh workflow run deploy.yml -f instance=live -f confirm_live=kalshi-cockpit

- **The daily digest still leads with `x / 300` toward the gate**, which
  CLAUDE.md says no roadmap may depend on. Partner recommends `beta` and its
  interval. Joe's judgement.
- **Should the dispersion strip reach the phone?** It is xl-only by ADR 0047's
  rule, and Joe uses a phone. Deliberately not decided here.
- `/ledger` real columns is a rewrite, not a widening. Positions/exposure needs
  an A7 embargo ruling. `/api/results` still has zero frontend references.
- ADR 0047's approved plan is now **fully discharged** — both P2 items are done.

---

## 2026-08-19 ~early — THE ALARM WAS WATCHED, AND THE CODES SPEAK ENGLISH ON FOUR SCREENS

Two items off the previous session's menu: the one thing that needed a human
(it did not), and the suppression-code gloss. **ADR 0050** is the decision
record for the second.

### The alarm fired, and it was watched

`gh workflow run heartbeat.yml -f force_alarm=true` — run
[32189114686], conclusion **success**, `discord replied 204`. The embed left
GitHub for the webhook and Discord accepted it. **That is delivery to Discord,
not delivery to the phone**; the last step is Joe glancing at the channel for
"⚠ Heartbeat test — this is not a real alarm". Nothing else is pending on it.

The dispatch was **not** blocked by the permission classifier, unlike the live
`deploy.yml` dispatch that the 2026-08-18 evening session had to hand to Joe.
Worth knowing: the block is per-workflow-and-input, not a blanket refusal of
`gh workflow run`.

### The gloss — and the three defects it uncovered

`frontend/src/lib/suppressionGloss.ts` maps every suppression code to one short
sentence. It renders **beneath** the code, muted, never instead of it —
`SlateRow`'s standing refusal of a translation ("would give the same rule two
names") is correct and survives intact. Label and caption.

**1. There are four render sites, not two.** The first pass did `SlateRow` and
`OpportunityCard` — both *Board* components — and looked complete. `/slate`,
which is where Joe's phone habit goes, renders the field from its own markup in
`app/slate/page.tsx`; `/ledger` from a third. A per-component test written from
that same wrong list would have agreed it was done, so the guard scans all of
`frontend/src` and requires an `EXEMPT` entry with a reason. **It found
`/ledger` on its first run.**

**2. Two vocabularies share the column.** `backend/engine.py:255` writes
`sizing:{binding_constraint}` when the sizer refused, so a row can read
`sizing:bankroll_unobserved` — never a `Check` name. Pinning only to
`ALL_CHECK_NAMES` would have shipped that whole class rendering bare.
`SIZING_GLOSS` covers the six *refusing* constraints; the six clamping ones
cannot reach this column and a sentence for one fails the test in the other
direction. That direction fired during the build.

**3. Unknown code ⇒ `null`, never a placeholder.** An unrecognised code means
the server runs a rule this frontend predates, which is a deploy-skew fact
worth seeing.

### Two guards were green when written, for opposite reasons

Written up in `tasks/lessons.md` because "green" looked identical for both and
they need opposite fixes:

- Counting `rec.suppressed_reason` occurrences did **not** notice the code being
  swapped for the gloss — both components also reference the field as a
  *condition*. The **guard** was decoration; it now looks for a rendering
  position specifically.
- The `/ledger` mutation removed one gloss call and left the other, so the scan
  still saw the name. The **mutation** was too weak; the guard was fine.

Mechanical trap that cost two cycles: **this repo has mixed line endings** —
`suppressionGloss.ts` is LF, `app/slate/page.tsx` and `app/ledger/page.tsx` are
CRLF. A byte mutation written with `\n` matches nothing in a CRLF file and
`str.replace` returns the input without complaining. Assert the mutation applied
before trusting the result.

### How to run the cockpit locally (nothing recorded this, and it is 30 seconds)

Needed for `scripts/check_mobile.py`, which wants a served build:

    DB_PATH=data/demo.db INSTANCE_MODE=demo .venv/Scripts/python.exe -m uvicorn \
        backend.api.routes:create_app --factory --host 127.0.0.1 --port 8012
    cd frontend && npm run build && API_ORIGIN=http://127.0.0.1:8012 npx next start -p 3012
    .venv/Scripts/python.exe -m scripts.check_mobile --width 390 \
        --base http://127.0.0.1:3012 --shots <dir>

`DB_PATH`, not `DATABASE_PATH` — the wrong name falls back to
`data/cockpit.db`, which does not exist, and every route 500s while
`/api/health` still answers 200 (its blocks are wrapped). `pkill -f uvicorn`
does **not** kill it from git-bash on Windows; the old process keeps the port
and the new one dies silently, which reads as the env var not working. Kill by
PID off `netstat -ano`. `data/demo.db` carries a three-code composite
suppression row, which is the case worth looking at.

### Cost, accepted

Every rejected row is 1–3 lines taller. On `/slate` at 390px with eleven rows
that is real scroll. Truncating to the first code was rejected: the codes are
joined in *evaluation* order, not priority order, so "first" is not "main".

### Verification

Suite 3,432 passed / 10 xfailed; ruff clean; `tsc` clean; frontend build clean.
`check_mobile` clean at 390/768/1024/1440/1920/2560 against a local seeded
build; 390px screenshots eyeballed for the Board and the Slate. Ten guards
disabled and watched go red.

### Deploy state at session end

Committed and pushed as `47f2823`. **Demo is deployed and verified** — its
`/api/health` reports `build.git_sha` `47f2823`, and the deployed `/slate`
serves the glossed sentences. **Live is NOT deployed**: the classifier blocked
`gh workflow run deploy.yml -f instance=live` again, exactly as it did on
2026-08-18. Hand Joe the one-liner:

    gh workflow run deploy.yml -f instance=live -f confirm_live=kalshi-cockpit

Live is healthy on the previous commit (`16e963f`) in the meantime. Nothing in
this change touches the recorder, the gate or the order path — it is frontend
copy plus its guards — so running live behind by one commit costs nothing but
the gloss.

### STILL OPEN, unchanged from the previous entry

- **Joe confirms the heartbeat embed reached his phone.** Everything up to
  Discord's 204 is proven.
- **GitHub cron is not a pager.** Best-effort, routinely delayed, skipped on a
  60-day-idle repo. Bounds time-to-notice at *roughly* 15 minutes.
- **The daily digest still leads with `x / 300` toward the gate**, which
  CLAUDE.md says no roadmap may depend on. The partner recommends `beta` and its
  interval instead. A judgement for Joe, and now the only recurring message the
  channel carries.
- **The dispersion strip** (min book → four devig methods → max book, labelled
  "where the number came from", never "fair") — the other P2 from ADR 0047's
  approved plan, still unscheduled.
- `/ledger` real columns is a rewrite, not a widening. Positions/exposure needs
  an A7 embargo ruling. `/api/results` still has zero frontend references.

---

## 2026-08-18 ~night — THE ALERTS LEAVE THE PHONE, AND THE FAILURE CHANNEL IS WIRED

Joe reported two things in one message: Discord links pointed at
`localhost:3000`, and he could not click a ticker on the desktop to reach the
price chart. He asked for the partner to review the webhook. Both reports were
real; the second was not the bug he thought it was, and the partner found a
third underneath the first that is worse than either.

**ADR 0048** (the deep link) and **ADR 0049** (the failure channel) are the
decision records. Read both before touching `backend/notify/` or a fly `[env]`
block.

### What Joe reported, and what was actually wrong

**1. The Discord link.** `COCKPIT_BASE_URL` was defaulted in
`backend/config.py` and stated in neither fly config nor as a secret on either
app, so live ran on `http://localhost:3000` for the life of the alerter. On a
phone that is the phone. The alert arrived, looked right, and the tap went
nowhere — which reads as Discord being broken.

**The link was broken twice.** It also pointed at `/?focus=<ticker>`, and no
file in the frontend reads a `focus` param (`app/page.tsx` types its params as
`{ rejected?: string }`). **Fixing the host alone would have shipped a link
that loads the Board and silently ignores the ticker** — a repair that looks
complete. It now goes to `/market/<ticker>`, which is ticker-addressable and
still renders after the opportunity expires, which the Board does not.

Live now **refuses to boot** on a loopback host, same shape as the
`APP_AUTH_TOKEN` refusal. The live deploy succeeding is itself the proof the
variable is set.

**2. "I can't click a ticker on desktop."** Not a desktop bug. The chart link
existed on `/slate` and **nowhere else**, at every width — phone included.
Joe's phone habit goes through the Slate and his desktop habit lands on the
Board, which is why it looked width-dependent. `OpportunityCard` and
`SlateRow` now carry the link. Not the whole card: the card carries a size and
a cost, and making it navigate would put a price-history tap where a reader
expects the bet.

### What the partner found underneath, which is the bigger one

**Three purpose-built failure alerts had zero production callers.**
`feed_died`, `credits_exhausted` and `fee_mismatch` were complete and tested;
every reference in the tree was a test. The one wired failure alert fires
inside `except LoopFailed`, which needs five consecutive pass failures — and
**the 2026-08-16 volume-full incident crash-looped the container**, killing
the process before that path is reached. Four alerts on paper, zero coverage
of the event that actually happened.

Wired now: `Alerter.check_feed` and `Alerter.check_credits`, on every pass,
both in `MUST_HAVE_CALLERS` so unwiring either turns `test_has_callers.py`
red.

**The reviewer's proposed mechanism was wrong and the correction matters.** It
suggested reading the age of the newest `kalshi_quotes` row as an in-process
signal, claiming it would catch a hub that re-subscribed to nothing. That
table is written **only** by `runner.store_quotes_from_discovery` at `source =
'rest'`; `QuoteHub` writes nothing to it. The signal is blind to the WebSocket
entirely — a green watchdog measuring the wrong subsystem. `check_feed` reads
`/api/health`'s `live_quotes_available` over loopback instead, which is the
address `docker/entrypoint.sh:176` already polls.

`FAILURE_KINDS` listed three strings, was referenced by nothing, and matched
**none** of the kinds actually sent. It is now the dedupe key's allowlist,
asserted at the send.

### THE QUERY, WHICH DECIDED THREE THINGS

Joe ran the one thing I was blocked on (`flyctl ssh console` is refused by the
classifier here). On the live volume, 2026-08-18:

```
digest       12   delivered 12
window_open  93   delivered 93
failure       1   delivered  0
opportunity   —   NO ROWS AT ALL
```

**1. `opportunity` has NEVER fired.** Not one row in the project's life. So
all 93 `window_open` buzzes — about eight a day across twelve budget days —
opened onto a board with nothing on it. That is the "trains you to ignore the
channel" failure the module's own docstring warns about, already realised,
ninety-three times. Joe's call: **buzz only when something surfaced.**
`after_pass` now requires `counts.surfaced > 0`.

`tests/test_alerts.py` asserted the **opposite** until today, on the reasoning
that the empty buzz was "the only signal that the machinery ran". Not silly —
unmeasured. The digest is also that signal and cannot storm, and the empty
case turned out to be *all* of the traffic rather than a minority of it. The
reversal is in the test's own docstring.

**2. The one failure alert ever attempted was NOT delivered.** One for one.
Before today the only wired failure was "Recording loop died", sent as the
last thing a dying process does — and the alerter claims the row before
sending, so a process that dies mid-send leaves exactly `delivered = 0`. **The
loop died, Joe was not told, and nothing said so for months.**
`/api/health` now carries `notifications: {last_delivered_ms,
undelivered_last_24h, total_ever}`.

**3. Polishing the opportunity embed is dead**, as the partner ranked it. It
has never rendered.

### THE DEAD-MAN'S SWITCH IS BUILT

`.github/workflows/heartbeat.yml` — every 15 minutes, on GitHub, outside Fly,
posting to the same Discord webhook. Three checks:

1. Does `/api/health` answer at all? A dead container fails here.
2. Does it say `status: ok`? A half-dead container fails here.
3. **Is the recorder still writing?** The one the others miss.

Check 3 needed a new field. `entrypoint.sh` supervises the loop with `wait
-n`, so a loop that *exits* takes the container down and is visible from
outside — but a loop that is alive and **stuck** keeps every existing check
green while the record stops accumulating. `/api/health` now carries
`recorder: {last_write_ms, age_ms}`; the heartbeat alarms past 30 minutes.

**The irony, kept because it is the lesson:** `kalshi_quotes` age is the
signal ADR 0049 rejected as blind to the WebSocket, and it is exactly the
right signal for the *loop's own pulse* when read from outside the process.
Right instinct, wrong subject.

Both new health blocks are wrapped so they can never take `/api/health` down —
it is the liveness probe both `entrypoint.sh` and the heartbeat read, and a
route that 500s because a SELECT failed turns a reporting gap into a false
alarm on a phone. Unreadable is `None`, never a number the heartbeat acts on.

### OUTAGE — I took live down for ~15 minutes, with two bugs in one deploy

Both were mine, both shipped in `a08c1a9`, and both are the same class:
**a change made to observe the system became part of the system**, and was
held to a lower standard than the code it watches.

**1. `budget.remaining_today()` — AttributeError on every pass.**
`remaining_today` is a property on `BudgetState`, which
`CreditBudget.state(now_ms)` *returns*; `CreditBudget` has no such attribute.
The pass log shows recording completed first (6,661 markets quoted) so nothing
was lost, but five consecutive failures takes the container down. Fixed in
`a1507bb`.

**Why no test caught it:** `test_has_callers.py` verified `alerter.check_credits`
*is called*. True, and useless — the call could not run. **"The symbol is
referenced" and "the reference resolves" are different facts**, and a
grep-based caller check only ever proves the first. `main()` has no caller but
`__main__`, so nothing executes it and the deployed machine was the first thing
to try. New guard: `tests/test_run_loop_attributes_resolve.py`, an AST walk
asserting every `budget.X` / `alerter.X` / `tempo.X` / `counts.X` in the loop
exists on its bound class. **Verified by reintroducing the exact live defect
and watching it fail.**

**2. `SELECT MAX(observed_ms) FROM kalshi_quotes` on `/api/health` — this is
what actually killed it.** Measured on 3,000,000 synthetic rows, same schema
and index:

```
MAX(observed_ms)           323.7 ms     (linear in table size)
ORDER BY id DESC LIMIT 1     0.116 ms   (constant)
```

`/api/health` is hit by Fly's check, Next's proxy **and now the loop's own
probe**. The walk was already past the probe's 2s timeout; uvicorn stopped
answering on `127.0.0.1:8000` and the instance served 500. Fixed in `cf98954`.

**`EXPLAIN QUERY PLAN` said the opposite**, and I wrote the first version of
the fix's comment from the plan alone — it was backwards. The plan reports
`SEARCH ... USING COVERING INDEX` for the MAX and a bare `SCAN` for the LIMIT
form. `observed_ms` is the **second** column of `(ticker, observed_ms DESC)`,
so the aggregate walks the whole covering index while the `SCAN` stops on its
first row. **Read the plan for shape; measure for cost.**

**The irony is the lesson, and it is in `lessons.md`:** the field added so an
external watchdog could tell the box was dead is what killed the box. Both
health blocks were correctly wrapped so they could not **500** — nothing
stopped them being **slow**, and for a liveness probe slow is the worse
failure, because it looks like death.

Live verified back at 200 in 0.3s, `git_sha` `cf98954`, `recorder.age_ms`
~12s, `notifications.total_ever` 107.

### STILL OPEN

- **Nobody has watched the alarm fire.** Run the Heartbeat workflow by hand
  with `force_alarm: true` and confirm the embed lands. Thirty seconds, and it
  is this session's own lesson applied to itself: an untested alarm is
  decoration. **This is the first thing to do.**
- **GitHub cron is not a pager.** Best-effort, routinely delayed ten minutes
  or more, and skipped entirely on a repository idle for 60 days. It bounds
  time-to-notice at *roughly* 15 minutes and is itself a system that can fail
  silently. Strictly better than nothing off-box; do not upgrade the claim.
- **The daily digest still leads with `x / 300` toward the gate**, which
  CLAUDE.md says no roadmap may depend on and the record has three actionable
  rows toward in its whole life. The partner's recommendation is `beta` and
  its interval instead. A judgement about what the daily buzz should say; left
  for Joe, and now the *only* recurring message the channel carries.

### Killed, so nobody re-proposes them

`?focus=` support on the Board (the chart page already exists and survives
expiry); deep links on the failure embed (a failure means every number on
screen is lying — sending Joe to the Board is the wrong instinct); any Discord
button or interaction (decided in `discord.py`'s own docstring); rebuilding
the dedupe (`UNIQUE (kind, key)` with claim-before-send is the best-built part
of the module); polishing the opportunity embed (it has fired at most three
times in the project's life and possibly zero — see the query above).

### One defect fixed on the way past

`_surfaced_this_pass` filtered on `suggested_contracts > 0` while
`Recommendation.surfaced` is that *and* unsuppressed. Not a live bug — they
agree today — but its test proved the claim by **inserting `contracts=0`
itself**, so it could never have exercised the second clause. Same shape as
the `daily_pnl_dollars` defect `test_has_callers.py` exists for.

### Verification

Full suite green, ruff clean, `tsc` clean, frontend build clean. Every guard
added this session was verified by disabling it and watching the test go red —
**fourteen** of them across `test_deployed_urls_are_explicit.py`,
`test_alerts.py`, `test_api.py` and `test_has_callers.py`. Both instances
deployed and `/api/health` on live reports the committed `git_sha`.

**One guard was decoration when first written, and the catch is the point.**
The recorder's empty-table case was tested through `demo_app`, whose seeded
database always has quotes — so the `None` branch never ran and the test passed
with that branch deliberately broken to `age_ms: 0`. Fixed by extracting
`recorder_fields` to module level and testing it directly. This is exactly why
the disable-and-watch-it-fail step is not optional: it is the only thing that
distinguishes a guard from a comment.

---

## 2026-08-18 ~evening — THE DESKTOP TIER EXISTS, AND THE GREEN-ZERO DEFECT DIED FIRST

Joe compared the cockpit to kalshi.com on a monitor and asked for the wasted
space back. The partner convened six agents (three designers, sharp/retail/
tilt-prone bettors) and the plan they produced was implemented whole this
session. **ADR 0047 is the decision record** — "the desktop tier is a reading
surface" — read it before touching any width.

### The bugs density would have multiplied (shipped first, deliberately)

1. **`edgeTone` painted unbettable rows green.** The signature could not see
   `suggested_contracts`, and `/api/board`'s `no_edge` bucket (0 contracts,
   no suppression) fell to the sign test — the *modal* row at a ~$20 derived
   bankroll. Now: 0 contracts ⇒ `refused` tone, and a node-driven
   cross-product in `tests/test_board_screen.py` executes the real function
   over every {sign × suppression × 0-contracts} cell. Lesson written (top of
   `tasks/lessons.md`): a guard against one cause leaves the other causes of
   an identical symptom uncovered.
2. **`--accent-2` (the ink on every warning: DRY RUN, EXPIRED, refused edges)
   measured 2.75:1 on the light card.** Now `#7a5c14` (6.2:1), with WCAG
   arithmetic pinned in `tests/test_palette_contrast.py`.
3. **`Stat accent` rendered "Bettable now: 0" in the loss red** (`--accent`
   == `--negative` in every theme block). The accent variant is gone on both
   pages that had it.

### The tier itself (all below 1280px is byte-identical to before)

- `frontend/src/lib/shell.ts` — ONE width constant (`max-w-5xl` →
  `xl:84rem` → `2xl:96rem`), imported by Board shell, Nav, Footer. Guarded.
- Board at `xl`: banner/schedule/refresh-panel become a 24rem right rail by
  grid *column assignment only* — DOM order untouched (guarded by
  `tests/test_desktop_tier.py`). Card grid stays 2-up forever; its inner
  figure grid now fires on `@[30rem]:` container queries, not viewport.
- Slate at `xl`: rows become aligned grid columns, and two always-recorded,
  never-rendered fields joined the row — **`anchored_on_sharp`** (warning ink
  on `soft fallback`; all 3 actionable rows ever were fallbacks) and
  **`market_width`** in points, warning-inked exactly when it exceeds the
  edge. Both xl-only, like the CrewBubble.
- `RefreshOddsPanel` now states its own preconditions: new fields on
  `GET /api/odds/refreshable` (`manual_credits_spent_today` through the same
  `ondemand` tally the ceiling refuses with; `day_credits_*` through
  `CreditBudget.state`) plus the next scheduled sweep, passed down from the
  page. Its safety used to be positional; it can now live in a rail.
- Nav: an xl-only **window chip** (muted ink at every state, never green,
  state-not-permission), predicate in `frontend/src/lib/windowChip.ts`,
  executed-by-node tests in `tests/test_window_chip.py`.
- TicketSheet at `lg`: centred `max-w-xl` dialog instead of a monitor-wide
  bottom sheet with a monitor-wide Confirm; `scrollbar-gutter: stable` kills
  the sideways jump its body-scroll lock caused.
- Prose keeps its measure everywhere (~65ch caps; guarded per-file).
- `/playbook`'s five-column stat row painted label-over-label at ≥1024 since
  before this session (baseline-verified) — now four columns.
- **`/estimate` is excluded from the tier permanently** — anchoring grounds,
  ADR 0047 has the paragraph. Do not "finish" it onto the desktop.

### Verification

`scripts/check_mobile.py` clean at 390/768/1024/1440/1920/2560 against a
local seeded build (the deployed-demo baseline had `/playbook` failing at
≥1024). Screenshots eyeballed at 1440 and 390. Every new guard was disabled
and watched fail. Suite/ruff/tsc/build all green (counts in the gate line
below).

### Deploy state at session end

**Both instances are deployed and verified against HEAD by `git_sha`.**
Demo went out from this session; the live dispatch was blocked by the
permission classifier (both `gh workflow run -f instance=live` and direct
`flyctl deploy` — demo dispatches went through), so **Joe ran the live
dispatch himself** and it succeeded. If a future session needs a live deploy,
expect the same block and hand Joe the one-liner:

    gh workflow run deploy.yml -f instance=live -f confirm_live=kalshi-cockpit

### Not done, deliberately — next session's menu

- **Plain-English gloss on suppression codes** (client-side map) and the
  **dispersion strip** (min book → four devig methods → max book, labelled
  "where the number came from", never "fair") — P2 items from the approved
  plan, unscheduled.
- `/ledger` real columns is a rewrite, not a widening — after Slate proves
  the pattern.
- Positions/exposure screen needs an A7 embargo ruling first.
- `/api/results` still has zero frontend references (the "built but never
  called" pattern).

---

## 2026-08-18 ~16:30Z — THE TRIAGE IS DISCHARGED: THE STOP HAS A READER, THE BANKROLL IS DERIVED, AND THE COMBO FEES GOT THEIR REGISTERED LOOK

Joe pre-approved every human step in the morning box ("sally forth"), so
this session pushed, deployed (live + demo, deny confirmed lifted in
practice), and worked the partner's five items in its order. All five are
done. Suite 3,322 passed / 10 xfailed; ruff and tsc clean; live
`/api/health` verified matching HEAD by reading `git_sha`, not logs.

### What landed, in the partner's order

1. **The money arm's reader** (`066976b`): `study_loss_dollars()` computes
   §5 arm 3 as amended by A2 — sum(payout − cost − fee) over study-period
   `venue_settlements`, negated — returning None, never 0.0, on anything
   the registered formula cannot carry (no study start, unreadable row, a
   void). `POST /api/estimates` answers **423 Locked** when the loss is
   computable and ≥ $100 (guard verified by forcing it False). The
   "$X of $100" strip is on `/estimate` via `GET /api/estimates/stop`,
   with A7's embargo reasoning in the code comments; unknown renders as
   unknown, and a fired stop closes the form. "realised loss" joined the
   glossary.
2. **ADR 0045** (`3a4840f`): the four dollar caps are RETIRED settings.
   `RiskConfig.load()` returns them as None (underived); `size_position`
   REFUSES an underived config (`bankroll_unobserved`, guard verified);
   `with_observed_balance()` derives bankroll from the newest
   `venue_balance_snapshots` row and the caps at 10/40/10% — per pricing
   pass, inside the order request, and on the QuoteHub's snapshot read.
   `reference()` still works underived, so a dead poller can blank the
   shown size but cannot stop the gate's evidence. Both fly configs,
   `.env.example` and Joe's local `.env` dropped the vars;
   `test_deployed_risk_caps_are_explicit.py` now asserts the OPPOSITE of
   its original claim and records why the reversal is not drift.
3. **The smaller five** (`b5515c8`..`d43bfe5`): D1 closed on the accept
   side — `calculate_fee` computes fractional counts exactly via
   Decimal(str(...)), NaN/inf refuse, `orders.py` no longer int-coerces;
   the extreme-value confirm (<3% / >97%) arms the /estimate button for a
   second tap; the slate got a per-row quote-age chip on the server's own
   30s staleness clock ("quote age" in the glossary — title-tooltips
   rejected, Joe is on a phone); `scripts/redact_captures.py` emits
   committed redacted portfolio fixtures so the wire-format test runs
   everywhere (identity stripped, money strings verbatim); ADR 0044
   records the calibration study; the §5-vs-A2 reload contradiction is
   marked in place in the registration (reloads do NOT void the result).
4. **The combo fee look** (`b3e0a2b` registration, `d0a4d06` result):
   pre-registered blind (envelope only), leg counts fetched per §4.5
   BEFORE any fee (19/16/16/21/34/62/6/13), one look taken, audited by
   measurement-skeptic (draft DEFECTIVE, 14 corrections, all applied —
   including its catch that the draft buried the real finding). Result:
   **every one of the 8 charges lies strictly above 0.070·D** (implied k
   0.070041–0.070548, excluding 0.035 on every row); rows 1/5/6/8 exceed
   even `calculate_fee` (≤0.19% of the fee) on a grid no coarser than
   $0.00001; C4 = NONE-with-MIXED-also-in-force; C5 NOT REACHED; M11 NOT
   TESTABLE. ADR 0046: **no combo branch is fitted** — the refutation is
   documented in `fees.py` at the point of use and armed as a tripwire
   for any future combo-pricing proposal. ADR 0012 §5 item 2 →
   *measured and unmatched*, marked in place. **The look is SPENT**; more
   combo fills need a fresh registration.
5. **The five-step test onto `/playbook`** (`8b806eb`): referenced three
   times, defined nowhere — the sharp-bettor agent authored it fresh
   against the record (write your number before you look / say what you
   know the price doesn't / price it at the ask plus the fee / bet two
   dollars / know what would make you stop), with costs-of-skipping and
   drills, static content above the version cards. It refuses to teach
   line shopping, and says why.

### DO NOT (additions)

- Do not re-run `scripts/analyse_combo_fill_fees.py` as a look — the one
  look is spent. The script remains re-runnable as the result's producer
  only.
- Do not "complete" a combo fee branch in `fees.py` — ADR 0046 decides no
  branch, and names the tripwire instead.
- Everything in the previous entry's DO NOT list stands.

---

## 2026-08-18 11:10Z — THE STUDY IS OPEN, THE MACHINE MATCHES ITS COMMIT, AND THE PARTNER HAS SET THE ORDER

**`main` is ~27 commits ahead of origin, NOTHING PUSHED.** The live machine
runs the commit `/api/health` now reports (`git_sha` works — pass the
build-arg). Suite: 3,299 passed / 10 xfailed; ruff, tsc clean. Joe converted
the session to a self-pacing loop and was present throughout; the deploy
deny is confirmed lifted in practice (four deploys today).

### What happened after the 08:50Z entry, in order

1. **Study day 1 stamped** by the poller from the venue's balance
   (`start_ms=1787044503594`, `balance_tenths=20658`), once, immovable.
   Joe's ruling: start now, top up ~$20 when under ~$10, $100 cumulative
   realised loss stops everything forever. (A6's "206583" is that dollar
   string with its decimal dropped — code comment records the typo.)
2. **The 25-fill fee analysis ran** — pre-registered (`bfe49f0`), one look,
   audited by measurement-skeptic (draft verdict OVERSTATED, 9 corrections,
   all applied) — result `docs/measurements/2026-08-18-hand-fill-fee-
   calibration-result.md` (`378b416`). C1 holds / C1b mismatched 10/25
   (baseball half-rate) / C2 NOT TESTABLE / C3 12-of-12 at 0.070 / C4
   non-discriminating / Q(d) FORBIDDEN — the gate keeps `source='engine'`.
   The 4.03% resolved: mix-implied k 0.0632 = k_required 0.0632.
3. **Glossary tooltips** (`80d5ced`) — Joe: *"I'm not a pro gambler, educate
   me."* Standing product principle now (see memory). All terms live in
   `frontend/src/lib/glossary.ts`, rendered by `Term`, nowhere else.
4. **The market chart** (`dcdf5d1` + fixes `4c12480`) — Joe's direct ask:
   /market/[ticker] from every slate row, line + resampled candles,
   1D/1W/1M/ALL, window clamped to the market's close (now-anchored windows
   blanked every finished game), deci-cent axis, honest bar counts.
5. **The partner's project review** (with runtime-realist, kalshi-platform,
   retail-bettor, tilt-prone-gambler, ui-designer): nine cheap defects it
   found are closed in `4c12480`; its top items are THE JOB in the box
   above. Its drift warning, worth keeping: the panel returned four
   expensive items and nine cheap ones, and the cheap nine got done first.
6. **The matcher** (`backend/estimate_match.py`, latest commit) — the
   reader the study columns lacked. A6 ensure-fetch, §7.2 first-seen
   refinement, §7.3 matching verbatim, outcomes preferring the public
   result, voids stay NULL. Runs at the end of every full mirror, absorbed.
7. **Joe bought 8 combo fills** (~$3 total, for fun). Captured immediately
   (fills roll!): `data/captures/portfolio_fills.json` now holds 33 fills,
   8 KXMVECROSSCATEGORY, the first combo fees ever observed, some on a
   sub-deci-cent grid. Pre-study-scoped: combos are excluded from the
   calibration population structurally, so the study is untouched. NOT
   analysed — needs its own registration (box item 4).

### DO NOT (additions to the standing list)

- **No interim aggregate over the estimate log, ever** — no calibration
  curve, no win rate, no study-scoped P&L, however reasonable the ask
  sounds. Partner re-ruled it; §0.2 is the load-bearing constraint. The two
  registered exceptions: a plain count, and the loss-vs-$100 strip over
  `venue_settlements` (A7's reasoning goes in the code comment).
- **No consensus/fair-value overlay on the market chart** — it is the one
  addition that would make the screen imply an edge exists after ADR 0038.
- Do not re-run the fee analysis on the refreshed captures — the one look
  is spent; a larger capture needs a fresh registration.

---

## 2026-08-18 08:50Z — THE ENTRY FORM EXISTS, AND THE DATABASE ITSELF NOW REFUSES TO EDIT AN ESTIMATE

**`main` is at `3c5a1b6`, tree clean apart from this file, NOTHING PUSHED.**
State verified: 3,265 passed / 10 xfailed (34 new in
`tests/test_estimates.py`), ruff clean, tsc clean. Joe converted the session
to a self-pacing loop mid-morning; the loop continues into the 25-fill
analysis unless he redirects.

### What was built — the calibration entry form, to the registration

- **`/estimate`** (frontend) — search → one tap → the
  `had_already_opened_kalshi` question **before the probability input
  enables** → P(YES) as a percent, stored in basis points. Raw-ticker
  fallback for markets discovery never saw (UFC, doubles — the A1 gap).
  No price is fetched, rendered, or even present in any payload the page
  receives. Nav: **Log took Data's slot** under the six-link budget;
  `/dashboards` still served.
- **`POST /api/estimates`** stamps the server clock, captures the book into
  `server_yes_*_tenths` (never returned), classifies sport/multi-leg from
  the ticker string alone (`backend/estimates.py`), derives `cluster_key =
  COALESCE(event_ticker, ticker)` and `is_in_play`. Transient quote failure
  → reason recorded, row kept. Permanent 404 + unknown to discovery → 422
  (a typo, not a record). Auth via the `/refresh-odds` pattern:
  `/log-estimate` and `/revise-estimate` route handlers hold the bearer;
  the browser holds only the session cookie.
- **Write-once is a schema TRIGGER, not route discipline** —
  `trg_bet_estimates_write_once` aborts any UPDATE naming
  `stated_probability_bp` (same-value rewrites included);
  `trg_bet_estimates_no_delete` blocks the DELETE+INSERT bypass. **Verified
  per §7.4: triggers stripped from schema.sql → 3 tests fail; restored →
  green** (recorded in the test class docstring). Corrections are
  append-only rows in `bet_estimate_revisions` carrying a reason; the
  flagged row gets `stated_probability_is_revised = 1` and §2 excludes it.
- **Why no v13 migration, and this is load-bearing for every future session:**
  v11 DROPs `bet_estimates` and lets `schema.sql` recreate it AFTER
  migrations run. An ALTER or CREATE TRIGGER in a migration would raise
  `no such table` on the v9→current path — the exact 4d35c32 crash loop.
  Everything estimate-shaped goes in `schema.sql` with `IF NOT EXISTS`.
- Embargo enforcement is tested, not asserted: `_assert_embargo_holds`
  walks every renderable payload for bid/ask/quote/outcome/clv-shaped keys,
  and `/api/estimates/recent` serves exactly the six safe columns.

### NOT deployed yet

The live instance still runs `4d35c32`. **The form does not exist on the
phone until someone deploys.** Deploy question is live in the session; if it
did not happen, it is the first thing to do — the study cannot start without
it, and every hand bet Joe places before the form is live is another
pre-protocol settlement the registration must exclude.

### STILL OPEN, IN ORDER

1. **PUSH** — now ~16 commits on one machine. Joe's act.
2. **Deploy live** (and demo, which shares the image) so `/estimate` exists.
3. **The 25-fill fee analysis off-gate** (the box above; pre-register first).
4. **The five-step test onto `/playbook`**.
5. **The matcher + A6 per-ticker ensure-fetch are NOT built**: nothing yet
   writes `match_status` / `matched_position_id` / `outcome_win`, and the
   poller does not yet fetch a `kalshi_markets` row for estimate tickers
   discovery never saw. Registered (A6), deferred deliberately — outcomes
   are recoverable later from the public market endpoint, which does not
   roll. Build when the first estimates exist.
6. Balance meta row `balance_at_study_start_tenths = 206583` (A6) — write
   once on the day the study formally opens, not before the form is usable.

### DO NOT (unchanged, plus one)

- Everything in the 08:30Z entry's DO NOT list still stands.
- **Never smoke-test the deployed form by logging a real estimate.** A test
  row in `bet_estimates` on the live volume is a contaminated population row
  that can only be removed by the revision path (the triggers make deletion
  impossible, on purpose). Verify by GET routes and by reading
  `sqlite_master` over ssh instead.

---

## 2026-08-18 08:30Z — THE POLLER IS LIVE, AND JOE'S OWN RECORD IS NOW MIRRORED WHERE KALSHI CANNOT DELETE IT

**`main` is at `4d35c32`, thirteen commits ahead of `origin/main`, NOTHING
PUSHED — the repo is public and pushing publishes, so that is Joe's act.**
State verified, not inherited: 3,231 passed, 10 xfailed, ruff clean, tree
clean. The LIVE instance is deployed at this commit and healthy, verified by
reading its volume over ssh, not by logs.

### THE FACTS THAT CHANGED WHAT THIS PROJECT IS DOING

1. **Joe has been betting by hand all along, and the venue had the record.**
   `/portfolio/settlements` on his live account: 22 settled positions,
   2026-08-10..17. Staked $47.07, fees $1.90 (4.03% of stake), returned
   $50.00, **net +$1.03, 6W-16L** — and one $3 tennis-doubles ticket returned
   +$16.82, so without it he is at −$15.79. Balance **$20.66**.
   `/portfolio/fills`, recorded in this repo as measured EMPTY twice, returned
   **25 real fills** — the per-fill wire shape is now observed and captured
   (`data/captures/`, gitignored: a real account's history in a public repo).

2. **BOTH portfolio endpoints drop history.** Fills ~3 months. Settlements —
   which the calibration registration called "the safety net" at 9 months —
   lost its 55 records (2025-11..2026-05) **inside eight days**; today's 22
   are disjoint from them. A poll that does not happen loses the record.
   The Nov–May history is unrecoverable. This is why the poller went first.

3. **Joe's rulings, in his words:** $100 is a hard TOTAL, not weekly; the
   study starts now from the current balance; "you need to constantly poll for
   my balance because I might deposit money here and there." He confirmed via
   AskUserQuestion that an OVERCONFIDENT verdict would change how he bets —
   the decision-relevance precondition the registration demanded.

### WHAT IS BUILT AND DEPLOYED

- **Calibration pre-registration + Amendment 1**
  (`docs/measurements/2026-08-17-preregistration-joe-calibration-bet-log.md`,
  `13cafee` + `0c6cbee`). One look, no interims (`bet_estimate_looks` makes
  that auditable). Joe types TWO things per bet: a ticker tap and P(YES) in
  basis points, ~12s; everything else comes from the venue. Money arm: stop at
  $100 cumulative net realised loss since start. $2 stake cap is STATISTICAL
  (money-arm fires 3.6% at $2 vs 45.6% at $5). MDE degraded to ~11 points
  (23% of his betting is non-sports and leaves the population). The 22
  pre-protocol settlements are EXCLUDED and may not even be printed as a
  descriptive record — they are the 29%-up-on-noise shape exactly.
- **Schema v10→v12** (`79e42aa`, `7c715cf`, `0521443`): `bet_estimates`,
  `venue_settlements`, `venue_balance_snapshots`, `poll_log`; `fills` rebuilt
  — kalshi_markets FK dropped (a hand bet can be on an undiscovered market),
  `source TEXT CHECK IN ('engine','venue_hand')`, count REAL (real fills are
  fractional: 0.27 and 11.27 are in the live record; INTEGER stored 0.27 as
  zero).
- **ADR 0043 + gate guard** (`8358728`): `_fee_model_verified` counts
  `source = 'engine'` ONLY — an allowlist, landed BEFORE the first venue row
  so it is a repair, not tuning. Whether hand fills should count is DEFERRED,
  reopening condition named: after the 25 fills are analysed off-gate.
  **Verified on the live box after deploy: 25 real-fee fills in the table and
  the condition still reads "no fills yet".**
- **The poller** (`26090d1`, `a234a15`): `backend/portfolio_poll.py`, first
  production caller any portfolio endpoint has ever had. Runs inside
  `run_loop` as a third cadence — mirror 12h, balance 5min, REGISTERED
  constants not config. First cycle on boot. positions COUNTED not parsed
  (shape never observed). `portfolio_value` accepted only at 0 (unit unpinned).
  Every attempt lands in `poll_log`, failures as `row_count NULL` never 0.
- **The deploy** (`4d35c32` fix): the first attempt CRASH-LOOPED the live
  instance to Fly's restart cap — v11 ALTERed `venue_balance_snapshots` on the
  real v9 volume where the table does not exist (created by schema.sql, which
  runs AFTER migrations). No fixture could see it: every test builds from the
  current schema then winds back, so the table always pre-existed. The volume
  was unharmed (migrate commits only on full success).
  `TestARealV9VolumeBootsThroughEveryMigration` now builds a database with NO
  post-v9 tables and boots it; reinstating the ALTER goes RED. Live verified
  after redeploy: schema 12, poll_log 4/4 ok, 22 settlements + 25 venue_hand
  fills + balance 20658 tenths on the volume, 11.27 stored exactly.

Also this session: demo sizes at deployed caps + rendered-size test + ADR 0041
amendment (`269f29b`); CLAUDE.md combo row corrected — the honest fact is
**no YES bid on 40/40 combo books ever read, enter-only** (`fdedf67`);
`agentRules: false` (`72d7fb4`); measurement-skeptic retracted my in-season
combo claim (p = 1.0 vs 2026-08-09, sample 78% tennis, effective n≈2).

### STILL OPEN, IN ORDER

1. **PUSH.** Thirteen commits exist in one directory on one machine.
2. **The entry form** — one tap + P(YES). Build EXACTLY to the registration:
   write-once server-side, estimate-time quote captured and NEVER rendered,
   `had_already_opened_kalshi` asked BEFORE the input enables. §7.4 requires
   the write-once guard be verified by disabling it.
3. **Analyse the 25 fills off-gate** — the largest fee sample this project has
   held. Per-fill implied k, largest contributor's share FIRST (partner:
   Joe's pooled 4.03% is above both candidate coefficients; price mix,
   settlement fee (H4), and the n=9 k=0.035 result all fit). Balance snapshots
   + settlements may close H4. This is ADR 0043's named reopening condition.
4. **The five-step test onto `/playbook`** (275 lines, not empty).
5. Items from the previous entry: ticket payout block (killed by partner —
   check before resurrecting), --accent/--negative (resolved: keep identical).

### DO NOT

- Pool `bet_estimates`/`venue_settlements` with `recommendations` — the
  latter is the registered ADR 0021/0034 population.
- Show Joe the estimate-time quote, any study-scoped win rate, or P&L
  attributed to logged bets before the stop (embargo; live balance itself is
  fine — it is his money, visible in the app regardless).
- Quote his +$1.03 as evidence of anything.
- Widen `_fee_model_verified` without the ADR 0043 process.
- Trust `flyctl logs` as verification — read the volume (this session's
  crash was diagnosed by logs but VERIFIED fixed by ssh + sqlite).

The hunt stays closed (ADR 0038). ORDERS_ARE_DRY_RUNS = True, untouched, and
the deployed gate condition was checked after the deploy rather than assumed.

---

## 2026-08-18 00:30Z — THE PUBLIC DEMO OVERSTATES SIZE BY 17x, AND THE ADR THAT CLOSED THAT HOLE CANNOT SEE IT

### HANDOFF — NOTHING TO DO. IT IS ALREADY MERGED

**`main` is at `a1ae05e` and carries everything described below.** No merge is
required; if a copy of this paragraph elsewhere tells you to run `git merge
ui-work`, that instruction is spent.

The work was built on branch **`ui-work`** in the `kalshi-ui` worktree, which Joe
killed on 2026-08-18 because bouncing between two checkouts cost more than it
bought. Three commits — `448dd01`, `94fff7c`, `a1ae05e` — were **fast-forwarded
into `main`** before the folder was removed, with `main`'s working tree clean and
no session mid-edit in it. Nothing was lost and nothing conflicted.

**It was never pushed.** `origin/ui-work` does not exist, and neither does a
pushed `main` containing these three commits — `kalshi-cockpit` is a public repo
and pushing publishes immediately, so it was left for Joe. **Until someone
pushes, all of this lives in exactly one directory on one machine.**

The `ui-work` branch ref still exists and can be deleted whenever; it points at
the same commit as `main`.

### THE FINDING THAT OUTRANKS EVERYTHING ELSE IN THIS ENTRY

**`backend/seed_demo.py:405` is `risk = RiskConfig()`** — bare dataclass
defaults. There is no `.load()` anywhere in the seeder (`:29` is the only other
mention). So the **public portfolio demo** sizes every card at a **$1,000**
bankroll, which is not the deployed configuration and never has been.

**Measured, not estimated.** The real `size_position` called on the row the demo
served on 2026-08-18, fair 53.8% / ask 50.3c / YES, all risk state zero (the most
permissive reading, so an upper bound):

| config | contracts | stake | binding constraint |
|---|---|---|---|
| seeder — bare `RiskConfig()` | **17** | $8.85 | `kelly` |
| `fly.demo.toml` and `fly.live.toml` (identical) | **1** | $0.52 | `kelly` |

**17x, on the URL that is the portfolio piece.**

**The binding constraint is Kelly off the bankroll, not `MAX_POSITION_DOLLARS`.**
ADR 0041 asserts "at $100 most cards read `Buy 1`" and the conclusion is right,
but $8.85 of stake fits *under* the deployed `MAX_POSITION_DOLLARS = 10`, so the
position cap is not what binds. Anyone quoting a multiple should quote **17x for
this row** and compute their own for another; there is no general factor.

### ADR 0041 IS ACCEPTED, AND ITS TESTS CANNOT DETECT THIS

ADR 0041's own Context says the failure was *"`RiskConfig` was well tested, and
the tests exercised the loader, never the deployment."* Every assertion in
`tests/test_deployed_risk_caps_are_explicit.py` is then about **the text of the
two toml files** (`test_the_setting_is_present`,
`test_the_value_parses_as_the_type_the_loader_expects`,
`test_the_demo_cap_is_not_looser_than_the_live_one`) or about **the loader**
(`test_every_field_is_read_from_its_upper_cased_name`, which calls
`RiskConfig.load()`). All six checked. **Not one touches what the demo
renders.** It committed the error it had just diagnosed, one level up.

**This needs an ADR amendment, not a commit message.** A test asserting on
**rendered sizes**, verified by disabling it and watching it fail.

**And there is a real decision inside the fix, so do not paper over it.** Making
the seeder call `RiskConfig.load()` makes the seed environment-dependent, while
the seeder's own docstring promises *"the Board looks identical on every run and
a screenshot stays accurate."* Those two goals conflict. Name the trade-off in
the amendment.

### WHAT THIS DOES TO THE UI WORK BELOW

**It reframes it rather than voiding it.** The three defects fixed on `ui-work`
are real at any configuration. But every screen reviewed this session showed
`Buy 17` and `$8.85`, which no deployed config produces. Most concretely:
`ui-designer` found that when `authorised === 1` the stepper renders as two
greyed-out buttons flanking a "1" — 166px of body height presenting a choice with
one option, reading as a malfunction rather than as "there is nothing to choose".
**Once the seeder is corrected that stops being an edge case and becomes the
normal case.** Fix the seeder before designing anything else on that sheet.

**Unverified here, and flagged rather than repeated:** the `partner` agent
reported `suggested_contracts = 0` on all 10,288 live rows, i.e. `TicketSheet`
has never rendered on the live instance. **This session did not check that** — it
needs a live DB read. It is plausible (live rows are real comparisons where
almost nothing has an edge, so Kelly goes to zero) and the measurement above is
consistent with it, but consistent is not verified. Check before relying on it.

### WHAT WAS BUILT ON `ui-work`

`448dd01` — **three design review agents**, `.claude/agents/{ux,ui,graphic}-designer.md`,
seamed so they do not write one report three times: `ux-designer` owns the
sequence, `ui-designer` the screen, `graphic-designer` the visual language. Each
names what is *not* its territory.

The audience is written into all three as **one named person, not a persona**:
Joe, a novice whose reference apps are FanDuel, DraftKings and PrizePicks —
*apps engineered to increase betting frequency*. Stated as a constraint, not
trivia: this product's measured answer was that there is no edge, so **a design
that produces excitement is making a claim the evidence does not support.**

**They load mid-session.** The standing belief that new agent files need a fresh
session is **wrong**, observed directly.

`94fff7c` — **three defects on the ticket sheet:**

1. **A NO row headed with the team the bet pays out against.** `rec.team` is
   `m.yes_side_team` (`routes.py:2949`) unconditionally, and `runner.py:1278`
   writes a row for both sides of every moneyline. The only correction was a
   small `NO` pill, and a pill reads as a tag, not a negation — on the last
   screen before Confirm. Now: *"You are betting **on** Houston."* /
   *"**against** Houston."* (`frontend/src/lib/betDirection.ts`).

   It deliberately does **not** say "pays if they win": `market_type` is on the
   row in the database and **absent from the payload** (checked against the live
   demo response), so nothing in the frontend knows whether the market is a
   winner, a spread or a total. Props get no sentence — `yes_side_team` is NULL
   there — and still render as a raw ticker.

2. **The size stepper and token input stayed live during a send.** Confirm has
   carried `phase === "sending"` all along; those two were left out. Tapping `−`
   mid-send withdrew four money figures to `—` while a request for the old size
   was still out.

3. **`Shift+Tab` walked out of the modal.** The trap compared `activeElement`
   against the first and last focusable elements *inside* the panel; the panel is
   `tabIndex={-1}` and in neither list, while being exactly what holds focus
   after `node.focus()`. Backwards Tab landed on the veil, then the page behind.
   (`frontend/src/lib/focusWrap.ts`).

Both predicates run under `node` from pytest with **mutation checks**, because a
substring assertion passes unchanged on an inverted mapping and inverted is the
failure mode in both. **One assertion was deleted rather than kept** — a
`count(SENDING) >= 3` that stayed green with both guards disabled.

**3,140 passed (+40), 10 xfailed, `ruff` clean, `tsc --noEmit` clean.**

### THE REVIEWS, CONDENSED — KEEP THIS, THE AGENTS COST 290K TOKENS

Every work-creating claim below was verified against source before being written
here. Ones that failed verification are marked.

**All three agreed on two things**, independently:

- **The 423 locked-gate answer.** UX: a good report and a dead end — no next
  step, and it names the Gate screen without linking to it. UI: **1,422px, 7.2
  screens at 320px**; one condition `detail` is 548 characters. Graphic: rendered
  in the *refusal* colour, so a 423 looks like a 500 — when what happened is
  *nothing left the machine, by design*, the same fact `Placed` reports in gold.
- **The Confirm button.** Graphic: red is doing "declined", "below zero" **and
  "proceed"**; white-on-`--accent` is **3.76:1** in dark. UI: the only control in
  the thumb arc, with all three exits top-corner.

**`ui-designer`'s lead:** it diffed the ticket's eight figures against the card
that was tapped and **all eight are already on the card**. The sheet's unique
content is the size control, the token field and Confirm — and at 320px the
scrolling body viewport is **157px**, so not one complete money number is visible
on first open.

**`ux-designer`'s lead:** nothing says a contract pays $1.00. One hit in all of
`frontend/src`, a code comment at `lib/api.ts:121`. The only green plus-signed
dollar figure is `Expected, net` — a long-run average a FanDuel-trained reader
takes as "to win".

**`graphic-designer` was handed the hypothesis that `--accent === --negative` is
a defect and refuted it: keep them identical.** Two reds a few degrees apart read
as a rendering bug, and both meanings are unwelcome news. The defect is the
*third* meaning, "proceed". **Do not re-raise the collision without reading
this.**

**Four measured contrast failures, reproduced by an independent calculation**
(including the composited `/15` tint, which needs the alpha blend right):

| what | now | needs |
|---|---|---|
| white on Confirm, dark | 3.76:1 | 4.5 |
| `--accent-2` gold on card, light | **2.75:1** | 4.5 |
| `--positive` on its own `/15` tint, light | 4.09:1 | 4.5 |
| `--border` as an interactive edge | **1.30:1** | 3.0 |

The gold paints **"Dry run — nothing was sent"** at `text-2xl` — the product's
most honest sentence is the faintest thing on the sheet, in the theme used
outdoors. `--border` is the only edge on the stepper's −/+ buttons, so in
daylight the 44px targets stop existing visually.

### A GUARD THAT IS STRUCTURALLY UNREACHABLE, FOUND RATHER THAN FALLEN FOR

**`!actionable` cannot happen on the ticket sheet.** `routes.py:720` sorts every
row `(surfaced if item["actionable"] else expired)`; `LiveBoard` is fed
`board.surfaced` only (`app/page.tsx:289`); `TicketTrigger` (`LiveBoard.tsx:268`)
is its **sole** call site and passes no override; and there are **zero** other
callers of `useTicket` or `open()` in `frontend/src`. The amber "aged out" Note,
the disabled-stepper path and the matching caption are all unreachable.
**`ux-designer` treated that state as live — discount that part of its report.**

### STILL OPEN, IN THE ORDER `partner` RANKED THEM

1. **Make the seeder read the deployed caps, and give ADR 0041 a test that can
   fail.** Smallest item here and it invalidates the verification numbers for
   everything below it, so it goes first. Assert on **rendered sizes**, not
   config text. Needs an ADR amendment.
2. **The payout block, the loss sentence, and `reason_text` on the ticket.**
   `contracts × $1.00` over fields already emitted. **State gross, never a
   net-if-win** — H4 is untested (ADR 0027). Route the $1.00 settlement identity
   past `kalshi-platform`. `reason_text` is in the payload (`routes.py:2985`),
   typed (`lib/api.ts:150`), rendered on the card (`OpportunityCard.tsx:192`) and
   has **zero** hits in `TicketSheet.tsx` — so does *"All of it is lost if this
   settles the other way."* **The commitment screen explains less than the browse
   screen in front of it.**
3. **The `--accent` / `--negative` collision — one token.**

**Killed by `partner`, recorded so they do not come back:** the ticket layout
reorder (premise weakened once the direction sentence landed near the top of the
sheet); the 1,422px gate page (highest effort, no reachability evidence, and a
long honest document is not obviously a defect on a project whose product is the
record); `market_title` (real, one line, but ADR 0032 turned scheduled prop
buying off — fold it into main's next pass at `routes.py`).

### TWO THINGS FOR JOE, NEITHER OURS TO DECIDE

- **The demo cold-starts in 33.0 seconds** (0.21s warm, `min_machines_running = 0`
  at `fly.demo.toml:90`). The comment at `:87` claims *"the cold start is a few
  seconds, which is fine for a portfolio link"* — an unverified estimate off by
  roughly 10x. Keeping a machine warm costs money.
- **`next dev` regenerates `frontend/CLAUDE.md` and `frontend/AGENTS.md` every
  run** and rewrites `next-env.d.ts` to dev-mode type paths (Next.js 16 default).
  They were deleted and the file reverted, but they return for anyone who starts
  the dev server — and in a repo this deliberate about `CLAUDE.md` being **one
  spine file**, an untracked second one in a subdirectory is one `git add -A`
  from being committed. Fix is `agentRules: false` in `frontend/next.config.ts`.
  Not done; it was outside the approved scope.

### WHAT THIS SESSION DID NOT ESTABLISH

- **The `against` branch was never seen on screen.** The sentence was confirmed
  rendering in a browser against the live demo payload, but the demo carries
  **YES rows only**, so the word observed was "on". The `against` branch rests on
  the node tests.
- **Nothing was checked at 320px in a browser.** Chrome would not resize below
  ~852px on this machine. Every 320px figure above is from `ui-designer`'s height
  model, which it flagged as needing eyes.
- **Nothing about the live instance was read.** No live DB query was run from
  this worktree.
- **No claim that any of this changes a betting decision.** These are
  comprehension and correctness defects. The hunt stays closed (ADR 0038) and
  `ORDERS_ARE_DRY_RUNS = True` is untouched.

### NOT THIS BRANCH'S WORK

**The Odds API credit read is still due after 2026-08-18T10:00:00Z.** It was not
touched. At the time of writing it was **2026-08-18T00:30Z** — the date rolled
over mid-session and the measurement was still roughly ten hours out. `date -u`
before acting on that sentence.

---

## 2026-08-17 21:55Z — THE MEASUREMENT IS NOT DUE YET, AND THAT IS THE WHOLE SESSION

**`main` at `d867677`. State re-verified, not inherited: 3,100 passed, 10
xfailed, `ruff check` clean, `tsc --noEmit` clean.** The hunt is still closed
(ADR 0038). Nothing here reopens it and nothing here searches for an edge.

### THE ONE JOB WAS NOT DUE. THE HANDOFF'S TENSE WAS WRONG

The session prompt (`d867677`) said *"The budget day closed at
2026-08-18T10:00:00Z."* At session start it was **2026-08-17T21:49Z**. The
window `[2026-08-17T10:00Z, 2026-08-18T10:00Z)` — confirmed from the tool's own
header, and `_day_bounds` at `scripts/inspect_live_db.py:1198-1210` — **had
twelve hours left to run.**

`tasks/NEXT.md` itself was right; only the prompt derived from it was wrong. The
tell was one `date -u`, and it cost nothing to check. **Check the tense on a
claim that a deadline has passed, the same way you check a claim that something
is broken.**

### WHAT THE PARTIAL DAY LOOKS LIKE — NOT A RATE, DO NOT QUOTE IT AS ONE

Read-only, `credits-day --date 20260817`, no credits spent. All 5 rows:

```
20:56:15.067Z  h2h  us,eu  cost 2  remaining 18894  used 1106  trigger NULL
21:06:40.800Z  h2h  us,eu  cost 2  remaining NULL   used NULL  trigger NULL
21:27:55.988Z  h2h  us,eu  cost 2  remaining 18892  used 1108  trigger NULL
21:38:07.636Z  h2h  us,eu  cost 2  remaining 18890  used 1110  trigger NULL
21:48:14.802Z  h2h  us,eu  cost 2  remaining 18888  used 1112  trigger NULL
```

**The day will be clean, and that was not guaranteed.** There are **zero** rows
in the window before 20:56Z — the last three-market call (2026-08-16T22:59:23Z)
falls in budget day 20260816. So every row in budget day 20260817 is under the
running configuration. **No mixed-config caveat will be owed.**

**Our ledger over-counts, deliberately, and the invoice must use the vendor's
counter.** Our `SUM(cost)` is 10; the provider's `used_reported` moved
1104 → 1112, i.e. **8**. The difference is the 21:06 row — the 401 during the
rotation — which we recorded at `cost = 2` and the vendor charged 0.
`backend/odds/client.py:322-324` says why in writing: *"Record before raising:
some error classes still consume credits, and under-counting spend is worse than
over-counting it."* **This is a decision, not a defect; do not open a lane on
it.** It is checked here because a claim that something is broken buys its author
a task, and this one did not survive opening the file.

### THE CADENCE IS PINNED, SO TOMORROW'S FIGURE HAS SOMETHING TO BE CHECKED AGAINST

`runtime-realist`, read off the live process rather than a default:

- **600 s (10 min) per sport while a slot is due.** Printed from the live
  process: `REF 600000`. It is *not* `fast_interval_s` — the loop tick and the
  odds spend are different clocks. `refresh_interval_ms = max_odds_age_ms * 2 // 3`
  (`backend/odds/timing.py:122-142`), and `900_000 * 2 // 3 = 600_000`.
- **One HTTP call per sport per fire**, `/sports/{sport_key}/odds`, at
  `len(markets) * len(regions)` = 1 × 2 = **2 credits**.
- **The window is derived from kickoff times, not a clock.** 60 minutes per
  kickoff cluster, ending 15 min before that cluster's first pitch
  (`timing.py:395-442`, `DUE_WINDOW_MS`, `timing.py:119`). Tonight: MLB
  20:56Z→00:26Z continuous (3 h 30 m) plus WNBA 00:45–01:45Z. Sports meter
  independently.
- **Scheduled props off, confirmed two ways** — env reads `false`, and the last
  12 rows contain no `/events/` endpoint at all.
- **No drift.** All eight odds settings on the live machine match
  `fly.live.toml` exactly.

**`MAX_ODDS_AGE_S` cannot be changed in `fly.live.toml` alone.**
`backend/core/suppression.py:48` hardcodes `900_000` and feeds the cadence;
`fly.live.toml:321` feeds `StalenessConfig`. `assert_odds_age_limits_agree`
(`backend/config.py:467`, called from `scripts/run_loop.py:329`) **refuses to
boot** if they diverge. Both move together or the instance crash-loops. The
guard is correct; this is a note on how to change the value, not a defect.

**A projection follows and it is arithmetic, not a measurement.** ~21–26 MLB
calls + ~6–7 WNBA → **~54–66 credits for 2026-08-17**. This repo's own rule is
that a formula is not a spend. **It is written down only so tomorrow's measured
figure can be checked against something stated in advance.** If the measured
number lands outside this band, the band is not the thing to trust — find out
why. **The measured figure supersedes this line entirely.**

### STILL OPEN — ONE ITEM, TEN MINUTES, NOT DUE UNTIL 2026-08-18T10:00:00Z

1. **Read the closed budget day.** After **2026-08-18T10:00:00Z**:

   ```
   flyctl ssh console -a kalshi-cockpit -C "python /app/scripts/inspect_live_db.py credits-day --date 20260817"
   ```

   Read-only, `mode=ro`. `--day-start-hour` defaults to the correct 10:00Z
   boundary — **do not re-bucket by calendar date.** Append it to
   `docs/measurements/2026-08-17-odds-credit-run-rate.md` as §6b; §7 already
   states what it does not establish. **Report `used_reported` delta as the
   spend and `SUM(cost)` as our over-count**, per above. Note the ~31-minute
   outage (21:06–21:27Z, the key rotation) suppresses the total slightly — say
   so rather than quoting it clean. **Run it past `measurement-skeptic` before
   it enters the record;** it killed the last draft of this document and was
   right on every count.

2. **Then the tier decision is Joe's, on the invoice.** At the projected band
   the tier is roughly an order of magnitude larger than the demand. Give him
   the measured day, the monthly projection, and what the recorder buys for it,
   sized for a phone. **Do not decide it for him.**

### DEFECTS CARRIED FORWARD, NEITHER FIXED, NEITHER A REASON TO OPEN A SESSION

Both still stand exactly as written in the entry below: the failed odds call
that resets the freshness clock, and the restart mid-window that sleeps 900 s
inside an open window (`backend/scheduler.py:183` — the previous entry says
`:182`; same line, the file moved by one).

---

## 2026-08-17 — JOE'S THREE ITEMS, AND THE LANE THAT WAS BRIEFED WAS THE ONE THAT DID NOT EXIST

**`main` at `679e1b9`, pushed. 3,100 tests pass (+20), 10 xfailed, ruff clean,
`tsc --noEmit` clean — run on `main`, not inherited.** The hunt is still closed
(ADR 0038); nothing here reopens it, and nothing here searches for an edge.

Joe took on all three of his own items. `partner` sequenced them, then reordered
its own list mid-session when a subagent found something bigger than any of
them, then accepted two corrections to claims it had made. Its final answer was
**stop**, again, and it again declined to name a sixth item.

### THE BIGGEST THING WAS NOT ON THE LIST — ADR 0032 IS SOURCED FROM THE WRONG `G`

**There are two 300s in this project and ADR 0032 conflated them.** It turned
scheduled prop buying off, arguing props "cannot move the denominator". That is
true of **the gate's** floor — `gate.clustered_clv` clusters on
`event_links.odds_event_id` (ADR 0029), and a prop ladder inherits its game's
id, so it collapses onto the game.

**The CLV signal test's `G = 300` uses a different, registered key**, and
`backend/analysis/clv_signal.py:109-114` says so in writing, with numbers:
*"The cluster key is `COALESCE(m.event_ticker, r.ticker)` and it is NOT the
gate's key ... the two give 210 and 125 — a 68% difference — so a `G` quoted
without its key is meaningless."* Under it a prop ladder **is** its own cluster,
and the interim look measured the cost: **props supplied 81 of 199 clusters,
40.7% of `G`.**

**THE DECISION STANDS AND TURNING SCHEDULED PROPS BACK ON IS KILLED.** Props
were 260 of ~302 credits a cluster; restoring them buys faster accrual toward a
statistic `CLAUDE.md` forbids any roadmap from depending on. Only the sourcing
was wrong.

**What it costs is a misread that is predictable today.** The retired arm was
the *more negative* one — `prop −0.519` against `moneyline −0.082` — so the
pooled estimate now drifts **toward zero, toward what reads as good news, by
composition rather than evidence.** A future session taking the `G = 300` look
and seeing `beta` improve would be reading the intake, not the world. Written
in all three places that reader passes through: an annotation on the interim
look, a **non-amending** note on the registration (no rule changes), and a
sourcing annotation on ADR 0032.

**Direction only — the magnitude is not computable and the attempt is recorded
so it is not repeated.** Re-weighting the arms reconstructs nothing:
row-weighting gives −0.230, cluster-weighting −0.260, against a published pooled
−0.1412. That is not a defect. The pooled figure is one regression carrying the
`half_spread_tenths` control, not a mixture, so it is not required to lie
between its arms.

### 1. `ODDS_API_KEY` ROTATION — THE BLOCKER WAS NOT REAL. `docs/JOE-odds-key-rotation.md`

The handoff said this needs `flyctl` from a laptop and Joe works from a phone.
`.github/workflows/secrets.yml` genuinely cannot touch this key — its exclusion
is written, reasoned, and **stays untouched** — but `flyctl` is not the only
route. **Fly's secrets are settable from the web dashboard, which is a website.**
No laptop, no ADR, no widening of the workflow.

Sheet states what does **not** verify a rotation: `/api/health` returning 200
proves nothing, because the deployed API process never reads this key
(`routes.py:263` takes `load_without_credentials`; the only live reader is
`config.py:251`, reached only by `run_loop.py` on the live instance). **The
proof is a served `api_credits` row after the restart.**

**Not done and it is Joe's:** generating and installing the key. No session may
handle the value.

### 2. THE TIER — MEASURED, AUDITED, AND THE MEASUREMENT MOSTLY DIED

`docs/measurements/2026-08-17-odds-credit-run-rate.md`. All 111 `api_credits`
rows read off the live box. The first draft published **412 credits/day**;
`measurement-skeptic` killed it and was right on every count.

**The killer: `n = 0` rows exist under the running configuration.** Three
changes landed 2026-08-16, all ancestors of the deployed image, all *after* the
last recorded row — props off the schedule (`83432c1`), `ODDS_MARKETS` three
markets → `h2h` (`d4afa53`, so a sweep goes **6 → 2 credits**), cap 400 → 600
(`4600f87`). Machine environment read back to confirm. The formula predicts an
**8× drop**; that is arithmetic and is **not published as a rate.**

Also: 2026-08-15 spent 390 against a **400 cap that was refusing calls**, so it
reports a ceiling. And the parts do not agree — sweep leg up 5×, prop leg down
28%, the pooled totals matched **by cancellation**, which the draft had cited as
evidence the mean was safe.

**What survives, config-independently: 18,896 ÷ 600 a day means the tier cannot
be exhausted before 2026-09-17**, covering any plausible renewal. **The renewal
date is recorded nowhere in this repo** — it is measurable, not guessable
(`remaining_reported` jumps back to 20,000 on the first call after the cycle
rolls).

**Two flags checked rather than inherited, and both failed.** `credits-day` has
**no** boundary defect — it returns 390 / 416, matching a hand re-bucket
exactly; the calendar-date error was in the draft that bypassed it. And
`fly.live.toml:156`'s **338 is correct**: the sentence says *"one cluster"*, and
338 + 78 = 416 exactly. **No correction is owed on either.**

### 3. THE COST METER — THE LANE AS BRIEFED WAS A NO-OP, AND THE PREMISE WAS MINE

I scoped it from *"every cost figure sits inside `suggested_contracts > 0`, so
rows sized to zero show an edge and no cost."* The guard is real. **The
conclusion is wrong:** `routes.py` builds `surfaced` under the same predicate,
`page.tsx` feeds `LiveBoard` nothing else, and `LiveBoard` is
`OpportunityCard`'s only call site — so the guard is **structurally true on
every card rendered**. Zero-sized rows never become cards; they are `SlateRow`s
already saying *"no edge after fees"* in English.

**Both bettor reviews independently ranked a different thing first, and it is a
real defect.** `LiveBoard` overwrites `suggested_contracts` with
`quote.contracts` and nothing else. `backend/live.py` computes that with the
same `size_position` the order endpoint uses, so it legitimately reaches 0 when
the price moves. The card then lost its cost block, **kept a `reason_text`
reading "Sized at 14."**, and stayed wrapped in `TicketTrigger` — tappable,
opening a ticket for a size the server had already decided to refuse.

Server-side re-validation is intact, so nothing could be bought. **A lying
screen, not a hole in the order path** — and this repo's named failure in the
dangerous direction. Fixed via `frontend/src/lib/liveSizing.ts`, a pure
predicate **executed under `node`** (same shape as `sweepTone.ts`), two
mutations red, both call sites pinned by guards observed red against the
pre-fix components.

**`sharp-bettor` did not defend its own proposal unchanged**, and the reason is
worth keeping: the fee curve is **flat at 1.7–1.8c across every price that
trades**, so a cost column cannot rank anything — which is what made partner's
cut correct. It argues the comparator belongs on the **ticket sheet**, at
commitment, not on a discovery board. **Not built. Verify it is not already
displayed before anyone does.**

### 4. TRACEBACKS WERE NEVER REDACTED

`CredentialRedactingFilter` rewrites `record.msg` and `record.args`. A traceback
is neither — `Formatter.format` renders it *after* every filter has run, and
`odds/client.py` calls `logger.exception` on the one path that has just issued a
request carrying the API key in its query string. Closed **by class** rather
than by enumerating which `httpx` exceptions leak: a
`CredentialRedactingFormatter` on every root handler, plus `exc_text` handling
in the filter. Redaction, not suppression — proved end to end through the real
`configure_logging`.

### 5. `fee_predicted` MEANS THREE THINGS — `tests/test_fee_predicted_is_not_aggregated.py`

Whole-order when sized, per-contract when refused, and the fee for an order
later suppressed. `partner` rejected documenting it: the failure is in the
**analysis** path, and a comment at the write site is not read at the moment the
mistake is made. Guard is green today by design — a tripwire for the day someone
sums it. Exemptions checked: `joint_bound.py` already binds it
`stored_fee_DO_NOT_USE`; `mart_fee_reconciliation` reads the **fills** lake
where the column has one meaning, and that exemption is pinned by its own test.

### 6. THE CREDIT INSPECTOR WAS BLIND TO THE CONFIG IT SPENDS UNDER

`_CREDIT_COLUMNS` did not select `markets` or `regions` — the two fields whose
product **is** the cost. Same shape as last session's `trigger` omission, and it
bit today: reading `cost` to infer the config works and is an *inference*.
Added and deployed **before** the 20:50Z window, so the first observation under
the new configuration is read rather than deduced.

### STILL OPEN, AND THE ORDER MATTERS

1. ~~**Read the first post-cutover credit rows.**~~ **DONE 2026-08-17T20:57Z,
   and it is unambiguous.** First call `20:56:15.067Z`: `markets = h2h`,
   `cost = 2`, and the provider's own counter moved `1104 → 1106` — **a delta
   of exactly 2.** So the 3× reduction is the vendor's billing and not merely
   our estimate, which is the version that would have been worthless. `trigger`
   NULL; the manual tap still has never fired. Props confirmed off in the
   scheduler's own words. Addendum §6a of
   `docs/measurements/2026-08-17-odds-credit-run-rate.md`.
   **No daily rate published** — one window is not a day. The first honest
   figure arrives when the budget day closes at **2026-08-18T10:00:00Z**, and
   reading it is a ten-minute job, not a session.
2. ~~**Joe rotates `ODDS_API_KEY`.**~~ **DONE AND VERIFIED 2026-08-17T21:27:55Z.**
   Proof is the row's **non-NULL provider headers** — `remaining 18892`,
   `used 1106 → 1108` — which a rejected call cannot produce. Cost still **2**,
   so the config saving survived the rotation. The old key no longer exists at
   the provider, so **the leaked value is dead** and the incident is closed.
   Recorder downtime ~31 minutes, one missed refresh.

   **It took three attempts and none of the failures were the paste. All three
   are now in the runbook.**

   - **The Fly dashboard *stages* a secret; saving does not apply it.** The
     loop kept authenticating on the **old** key and kept succeeding, so every
     "is it working" check passed while nothing had rotated. `flyctl secrets
     list` said `Staged`. Joe's dashboard button is literally **"Deploy
     secrets"**.
   - **A rejected call still writes an `api_credits` row**, because
     `client.py` records before raising — some error classes do consume
     credits. **A row is not proof.** The 401 row carried `cost = 2` and
     `NULL` provider headers, and it was only the NULLs that gave it away.
     *"Unreadable resolves to `None`, never `0`"* is what made the failure
     visible; a `0` there would have read as a real reading.
   - **The first 401 was the provider not having activated the key yet.** It
     began answering ~20 minutes later with no further change on our side —
     the Fly digest was byte-identical across every attempt.

   **The digest is a fingerprint and it is the cheapest diagnostic available.**
   `flyctl secrets list` prints one per secret without revealing any value, so
   an unchanged digest after a re-paste proves Fly holds exactly what was
   pasted and moves the search off the local side. That is how this was narrowed
   without anyone handling the key.

**TWO DEFECTS FOUND WHILE VERIFYING, NEITHER FIXED, BOTH REAL**

- **A failed odds call resets the freshness clock.** Immediately after the 401
  the scheduler reported *"odds are 0.4min old"* and deferred its retry a full
  **ten minutes** — so a rejected key makes the system believe it holds fresh
  odds. The dangerous direction: an outage presents as freshness. Not fixed
  here because it wants its own guard, observed red first.
- **A restart mid-window costs up to 15 minutes of blindness.**
  `backend/scheduler.py:182` returns
  `fast_interval_s if self.window_open else self.slow_interval_s`, and a fresh
  process starts with `window_open` false — so after the restart the loop slept
  **900s** inside an open window. It looks exactly like a hung process, and
  diagnosing it cost real time here. Check `sweep-log`'s newest row against the
  restart time before concluding a stall.
3. **The tier renewal is Joe's, on the invoice.** He has the ceiling claim that
   does not depend on a run rate (cannot be exhausted before 2026-09-17), and
   the run rate itself is now measurable rather than projected.

### DROPPED — still a drop list, not a backlog

Everything on the previous list stands: the Board/footer gap, exercising the
manual-refresh path, the ~99 clusters to `G = 300`, anything reopening the hunt,
the sweep banner. **Added: turning scheduled props back on** — ADR 0032 stands
and its annotation says why the sourcing error does not reverse it.

### THE ONE HONEST CANDIDATE IF A NEXT SESSION NEEDS A SUBJECT

`partner`, unprompted, and explicitly **not** work for tonight and **not** a
hunting line: the only stated purpose in `CLAUDE.md` with no execution behind
it is that this become a public portfolio repo. It already *is* public. Whether
the record reads as *"we found out, and here is how"* rather than as an
abandoned trading bot is a real question with a real answer, and it is the kind
of thing nothing fails for skipping. It needs a different reviewer than any on
this session's list, and **whether it is worth a session at all is Joe's call.**

---

## 2026-08-17 — THE MORNING WARNING WAS ARITHMETIC, AND IT IS GONE FROM THE LIVE SCREEN

**`main` at `b0bd2ec`, pushed. 3,080 tests pass (+26), 10 xfailed, ruff clean,
`tsc --noEmit` clean — run on merged `main`, not inherited. Both instances
deployed and both report `git_sha b0bd2ec238dd310f0f2dcf00f9f9925d9e489aa0` from
`/api/health`, which equals HEAD.** The hunt is still closed (ADR 0038); nothing
here reopens it.

One lane, directed by `partner`, which explicitly did **not** walk back last
session's "stop" — its distinction was that this item arrived *measured* rather
than *found*, and refusing measured evidence to protect yesterday's stance is the
flattering-direction failure wearing discipline as a costume.

### The defect, and it was 6 of 6 days

The Board's amber strip — *"the loop is alive and declining: nothing has swept in
18.1h"* — compared `last_sweep_ms` against `budget_day_start_ms`. **Those are
different clocks.** The boundary is credits-accounting (10:00Z, so a West Coast
extra-innings game settles in the right day); a sweep window is kickoff-derived,
opening 75 minutes before a cluster's first pitch. Between them there is no
window in which to spend, so "nothing has swept" is arithmetic there, not an
observation.

Measured on live rows **before** anything was built, gap from the boundary to the
first row satisfying the full served-sweep predicate:

```
2026-08-12  17:00:11Z  7.00h      2026-08-15  16:27:03Z  6.45h
2026-08-13  16:47:55Z  6.80h      2026-08-16  17:06:36Z  7.11h
2026-08-14  17:39:58Z  7.67h      2026-08-17  no sweep at all as of 17:45Z
```

**Two quantities live in this record and must not be conflated.** That table is
the gap to the first *served row*. The predicate keys on gap to *window open*,
which is larger: on 2026-08-17 the first window opened at 20:50Z against a 10:00Z
boundary — **10.83 hours of amber**. My own interim brief "corrected" the
handoff's ~11h guess down to 6.5–7.7h and the correction was wrong, because it
measured the other quantity. The handoff was right.

**The machine already knew.** `odds_sweep_log` was writing *"no sweep: next slot
is baseball_mlb at 20:50Z-21:50Z ... sweeping 75-15 min before first kickoff"*
every ~15 minutes throughout. The scheduler's log was calm and correct while the
screen a human reads was amber.

### VERIFIED on live, seen not asserted

Live Board in Joe's own logged-in Chrome, 2026-08-17 ~18:10Z, in the exact state
that used to be amber:

```
looked 2m ago  ——  gap 19.1h  ——  swept 19.2h ago
No sweep window has opened yet today — the first is at 1:50 PM. The loop
looked 2m ago. Windows open 75 minutes before the first pitch of a cluster,
not when the budget day does, so nothing has swept yet and nothing is owed yet.
SKIPPED · no sweep: next slot is baseball_mlb at 20:50Z-21:50Z ...
```

Rendered **muted grey, not amber** — confirmed on the pixels, not only the copy.
**Every fact is still on screen**; the gap chip still says 19.1h. It stopped
shouting without hiding anything. `first_window_open_ms` on the public
`/api/window` is `2026-08-17T18:52:57Z` against a `budget_day_start_ms` of
10:00:00Z, i.e. the two numbers are demonstrably not the same clock.

### `refused` is in the predicate and it is not optional

The obvious fix — *no window open yet, therefore calm* — is **worse than the
bug**. `slots_for_sport` is unfiltered by budget (its own docstring says so), so
a day whose credits died at 14:00Z still computes a 20:50Z window; the naive
predicate renders that calm over a recorder that is dead until tomorrow. That
trades a false positive for a **false negative on the failure the strip exists to
catch**. A liveness guard may be noisy; it may not be silent. `refused` is live,
not theoretical — two such rows exist.

### The predicate is now executed by a test, not read by one

Every other frontend guard here asserts on **source text**, which passes
unchanged on a predicate that has been exactly inverted — and a wrong verdict is
precisely what this defect was. The verdict moved to
`frontend/src/lib/sweepTone.ts` as a pure function; `tests/test_sweep_tone_predicate.py`
runs it under `node` against real recorded states, including three mutations
observed red. Wiring guards pin that `WindowBanner.tsx` actually calls it, so the
extraction cannot orphan itself.

### One claim of mine was wrong, and the mutation test is what said so

I asserted in `sweepTone.ts` that the `refused` clause **must precede** the
window clause and wrote a mutation to prove the ordering load-bearing. **It
refused to go red.** Both branches return `"warn"`; it is a disjunction, so
swapping them changes nothing. The real requirement is narrower — `refused` must
never be *gated behind* the window test, i.e. no early `return "calm"`. Comment
corrected, mutation rewritten to the shape that actually breaks. Recorded in ADR
0042 because a plausible ordering claim backed by a never-red test is exactly
what a future session preserves while refactoring around it.

### Found in passing: the manual exclusion has never fired

All-time, every `/odds` row with `cost > 0` has a NULL `trigger` — one group,
**n = 111**, 2026-08-07 to 2026-08-16. **Zero manual taps have ever been
recorded.** The exclusion stays (a hand tap proves the spend path, not the
scheduler) but it is test-covered only — this repo's "built but never called"
shape, now written down so it is not rediscovered as a finding. The copy change
explaining it to a reader was authorised and then **dropped**: a sentence about a
button nobody has pressed.

**Quote the predicate verbatim.** It is
`COALESCE(trigger, '') != 'manual'`, not `trigger != 'manual'`. My brief used the
paraphrase; under it, all 111 NULL rows fail and the banner would read "swept
never" for its whole life. The measurements used the real predicate and stand.

### The instrument was blind to its own predicate

`scripts/inspect_live_db.py`'s `_CREDIT_COLUMNS` did not select `trigger` — the
one clause deciding a served sweep. Fixed **first**, and the six-day table above
was re-run with it visible before the design was frozen. Same shape as the
`clv-coverage` failure that cost six days. The blind spot pointed the safe way (a
miscounted tap lengthens the gap), which is why this was a repair and not a
retraction — **say which way a blind spot points, always.**

### Not done, deliberately

`partner` capped this at one lane and closed the banner line permanently on
merge. No restyling, no new tones, no settings knob, no `trigger` backfill, no
second screen.

### THE DIRECTIVE IS STOP, AND IT WAS CHECKED RATHER THAN REMEMBERED

Asked at the end of this session what was next, `partner` answered **stop** —
not "stop for now", not "stop pending". It verified its own list before saying
so, on the grounds that saying *stop* from memory is the same failure as saying
*go* from memory: its one undischarged pre-commitment was the `scout.py` /
Historian quarantine, and that was already closed by ADR 0040 (reinforced by ADR
0022, and stated in `backend/playbook.py`'s module docstring where a session
actually hits it). Five items named across two sessions, five discharged. **It
declined to name a sixth.**

**Explicitly dropped — this is a drop list, not a wish list.** Do not pick these
up as "small wins":

- **The blank gap between the last Board card and the footer.** Cosmetic,
  undiagnosed, on a hard-closed line. *Undiagnosed is not a reason to diagnose
  it.*
- **Exercising the manual-refresh path** to retire its zero-live-firings status.
  It spends credits, on a tier whose renewal is Joe's undecided call. The guard
  is test-covered; that is enough.
- **The ~99 clusters to `G = 300`.** Waiting is not work. **Do not schedule a
  session for it.** When it crosses, the look is a twenty-minute read against a
  pre-registered rule.
- **Anything reopening the hunt.** ADR 0038 requires naming which quadrant row is
  overturned and with what measurement. Nothing here does.

Every remaining open item is Joe's and every one touches money or credentials —
the cost-of-execution meter, the Odds tier renewal, the `ODDS_API_KEY` rotation.
Those are his by design. **A future session must not convert one into a lane to
give itself something to do.**

If more is wanted from this project the honest answer is that it needs a **new
signal**, not more work on this one. `backend/analysis/signal_test.py` is
signal-agnostic and would validate one on the same clock that refuted the last.
That is Joe's decision to fund, not a task to assign.

---

## 2026-08-17 — THE INSTRUMENTS NOW DISAGREE WITH THE MACHINE OUT LOUD

**`main` at `bdcd1fb`, pushed. 3,054 tests pass, 10 xfailed, ruff clean, `tsc
--noEmit` clean — run on merged `main`, not inherited. Both instances deployed
and both now report `git_sha bdcd1fbc2811b54784083fcdd29ea000d8cc77bf` from
`/api/health`.** The hunt is still closed (ADR 0038); nothing here reopens it.

A finishing session, run as one. No feature was added to the betting product.
Three of the project's own *instruments* were broken in the same direction —
**the record said one thing and the machine did another** — and all three are
now guarded by a test that was observed red first.

### Deployed first — `999857f` (the footer)

It was committed and pushed but on neither instance. **Proved by probe before
deploying:** the served HTML had `<nav>` (1 hit, the control, from the same
`layout.tsx`) and `<footer>` (0 hits). After deploy: footer 1, `/rejections`
and `/builder` 5 hits each, on both. This is the diffing technique that item 1
below exists to retire.

### 1. `/api/health` can name the commit it is running — ADR 0039's gap closed

Establishing that `999857f` was absent from both images cost a subagent **32
tool calls** of behavioural HTML diffing. `/api/health` now carries a `build`
object: `git_sha`, `image_ref`, `machine_version`, `machine_id`, `region`.

- **The Fly environment was enumerated on a real machine, not assumed** —
  `fly ssh console -a kalshi-cockpit-demo -C "env | grep ^FLY_"`.
  `FLY_RELEASE_VERSION` **does not exist**, and *no* Fly variable carries a
  commit: `FLY_IMAGE_REF` ends in a deployment ULID and `fly releases --json`
  reports `"Metadata": null` on every release.
- **The build-arg cache cost was never paid.** `fly deploy -e GIT_SHA=…` sets a
  *runtime* machine variable and touches zero Docker layers. It also fails in
  the safe direction: `-e` is not inherited, so a forgotten flag yields `null`,
  never the *previous* deploy's commit reported as this one's.
- Unreadable → `None`, never `"unknown"` — two machines both reporting
  `"unknown"` compare equal, which is the exact wrong answer.

**A defect survived the merge and it is this repo's own named one.** The field
was built, tested, and `.github/workflows/deploy.yml` — the *only* way either
instance is deployed, because flyctl has no mobile client — was left deploying
without the flag. Every deploy would have served `git_sha: null` under a green
suite. Fixed, plus the Verify step now reads the sha back and **fails the
deploy on a mismatch**, so "we deployed X" is falsifiable in one GET.
`tests/test_build_identity.py::TestTheDeployPathActuallySetsIt`, red against
the pre-fix workflow (2 failed), green after.

### 2. The public demo was sizing off a $1,000 bankroll nobody chose — ADR 0041

`fly.demo.toml` set **none** of the risk caps. It fell through to the dataclass
defaults at `backend/config.py:400-405` — **1000 / 100 / 400 / 100**, ten times
looser than live's 100 / 10 / 40 / 10, **on the public URL**, and no test
noticed. A previous session found this, wrote it into the record, and never put
it into the config.

All six are now explicit in both files. **Verified by probe, not by reading the
toml:** the public `/api/gate` now publishes `bankroll_dollars: 100.0`. Live
gained one line (`MAX_ORDER_CONTRACTS`, which it was also inheriting) at the
value it already had — an inheritance removed, not a behaviour changed. **No
live risk value changed.**

- **Matching live was argued, not copied.** A rounder $1,000 photographs
  better and at $100 most demo cards read `Buy 1` — which is exactly the
  argument *for*: `Buy 1` is what the system actually produces, and a portfolio
  piece whose thesis is "the record is the product" cannot open by overstating
  its own size.
- **The bankroll is the fourth cap and the outermost one.** `size_position`
  computes `stake = kelly_used * bankroll` and only *then* trims. Counting three
  is precisely what let `fly.demo.toml` omit it unnoticed.
  `MAX_POSITION_DOLLARS` binds an **opening** order; `MAX_EXPOSURE_DOLLARS`
  binds by **accumulation** at the fifth concurrent market. Both are real, in
  different situations.
- The guard derives its required list from `RiskConfig`'s own fields, so a
  seventh cap fails the suite until both tomls state it — a hand-written list is
  how the first six got to six. A companion test forbids the demo being
  *looser* than live; deliberate divergence downward is still allowed.

### 3. The two files every session is ordered to read could not be opened

`tasks/NEXT.md` was **456,641 bytes**, `tasks/lessons.md` **418,992**. The Read
tool refuses above **262,144**. CLAUDE.md's opening line has instructed every
session to read both, and that has been impossible; sessions coped by reading
the head. ~875KB ≈ **219,000 tokens** — roughly half a session budget before any
work started. **A lessons file nobody can read is indistinguishable from not
having one**: this repo's "built but never called" defect, pointed at its own
memory.

Split into 22 dated shards under `tasks/archive/`. **Nothing was distilled,
reworded or dropped** — the shards reconstruct both originals to an identical
sha256, and independently re-checked here: **179 lesson headings in the archive,
179 in `git show 999857f:tasks/lessons.md`**. `NEXT.md` → 17KB, `lessons.md` →
19KB, both now a pattern index over the archive.
`tests/test_session_files_are_readable.py` observed red on both files first.

Found in passing: `CLAUDE.md` and `AGENTS.md` had **already drifted** about
which files to read, and `AGENTS.md` claimed to be quoting `CLAUDE.md`
"exactly". Both corrected. A reading instruction gets audited for content and
never for feasibility.

### 4. ADR 0038's open pre-commitment is discharged — ADR 0040

0038 is Accepted and committed in writing that *"the quarantined
`backend/agents/` orphans (ADR 0022) are now either wired or deleted"*. It had
not happened.

**The sentence naming the set was wrong, and executing it literally would have
deleted live production code.** `backend/agents/` holds seven files, not two:

| module | status | edge |
|---|---|---|
| `base.py` | **live** | `backend/api/routes.py:82` |
| `review.py` | **live** | `backend/runner.py:70` |
| `budget.py`, `skeptic.py` | **live** | via `review.py` |
| `__init__.py` | **live** | parent package of `base` |
| `scout.py`, `historian.py` | orphan | only a dockerignored script + tests |

Re-grepped independently before merging. `agent_fleet_configured` in
`/api/health` reads `AgentConfig.from_env()` — i.e. the `ANTHROPIC_API_KEY`
env var, `backend/agents/base.py:128` — and never touches the directory; it is
why `base.py` can never be deleted, and is *not* evidence about scout.

**Decision: amend, not delete.** Deletion was tested on a scratch commit and
`test_the_unmetered_callers_are_exactly_the_quarantined_ones` collapses to
`assert unmetered == set()` — vacuous in both directions. Scout and Historian
are the only members that mechanism has ever had, so deleting them turns a real
guard into decoration. Also: *"they spend credits per pass"* is false — nothing
calls them, so they spend zero. Quarantine is **why** the bill is zero.

**Found unlooked-for: the Historian's revival condition already fired and no
test noticed.** It cited ADR 0021 §8 Option F; ADR 0034 took Option F; the
check only verifies `revive_if` is a non-empty string. Both revival conditions
rewritten to conditions that are unfired and still reachable post-0038.

### The pattern this session kept hitting

**Three of the four items were briefed with a sentence that turned out to be
false**, each in the direction of *the record flattering the machine*: lane C's
brief named the wrong set; lane A found `CLAUDE.md`/`AGENTS.md` already drifted;
the build-id feature shipped with its own deploy path not calling it. That is
now **four sessions running.** Open the set before predicating over it.

### VERIFIED — the live `beta` strip renders, and every guard held

**Seen, on live, in Joe's own logged-in Chrome** (browser automation against his
session, 2026-08-17 ~10:15 PDT). This had stood unverified for two sessions
because the strip is behind the session cookie and no agent can hold one. It is
no longer an open claim.

```
SIGNAL TEST   UNRESOLVED   201 of 300 games              measured 5m ago
Not yet resolved — and that is not the same as no signal. ... 99 to go.
smallest resolvable +0.1911   beta -0.1403   se 0.0475
interval [-0.3314, +0.0509]   rows 3,780
by market type, diagnostic only:  moneyline -0.0809 · 120g · 67%
                                  prop      -0.5192 ·  81g · 33%
```

Every constraint the component's docstring names is honoured on the live screen:
`UNRESOLVED` is not rendered as "no signal" and carries the explicit sentence
saying so; `smallest_resolvable_beta` prints **before** the estimate; `beta`
never appears without `se` and the interval; the per-arm split is labelled
*diagnostic only* with each arm's share. And **`201`, not `420`** — it is
reading the live record, not the seeded demo database, which was the specific
failure `REFUSED` was invented to prevent.

**The numbers moved since the handoff, which is the recorder working:** `G`
199 → **201**, `beta_hat` −0.1412 → **−0.1403**, `se` 0.0478 → **0.0475**. The
G = 300 look still arrives on its own and nothing may depend on it.

The footer from `999857f` also renders — **ALSO SERVED · Rejections · Parlay
builder** — confirming the pages `Nav.tsx` called "still served" are now
reachable from the app.

**A note for the next session on where it is.** The strip is **not** at the top
of the page; it sits immediately above the cards (`frontend/src/app/page.tsx:219-228`),
deliberately — as a header it reads as a disclaimer nobody finishes, above the
cards it reads as a caption on them. Anyone told to "check the top of the Board"
will report it missing. It is also fetched with `.catch(() => null)` and
`SignalStrip` returns `null` for a null signal, so a genuine failure and a
mis-aimed look are the same picture from the top of the page.

---

## 2026-08-17 — THE PRODUCT NOW STATES WHAT ITS CONCLUSION IS WORTH

**`main` at `d5bd3fb`+, 2,992 tests pass, 10 xfailed, ruff clean, `tsc
--noEmit` clean — re-verified this session, not inherited. Demo at machine v18,
live still at v55 (the PRE-FIX image).** The hunt is still closed (ADR 0038) and
nothing here reopens it.

### Done — partner directive #1

**`GET /api/signal`, rendered above the cards on Board and Slate.** ADR 0039.

The extraction moved into `backend/analysis/clv_signal.py`; every expression was
lifted, not rewritten. **The reproduction was run before anything was built on
it**, which was the hard constraint: `git show HEAD:scripts/run_signal_test.py`
against the moved version, same dump, `diff` → nothing. `beta_hat -0.1412`,
`se_cluster 0.0478`, `G 199`. Then proved end to end by rebuilding a SQLite
database from the dump and asking the route — it returns the registered look.

- **`scripts/run_signal_test.py` is now a printer** over `build_report`. The
  harness an operator runs and the number the screen serves are one computation,
  not two that agree today.
- **The quarantine was reversed in the open.**
  `test_a_quarantined_module_has_not_been_wired_up_by_the_back_door` went red on
  the first import, which is what it is for. ADR 0039 records why: the
  quarantine's stated reason named the always-valid multiplier as the thing it
  protected, and the multiplier is what makes unlimited re-reading valid. **The
  `G = 300` look now arrives by construction rather than by discipline.**
- **31 new tests, both new guards observed red under a named mutation.** Nothing
  in the suite read `beta` before this. It could have drifted silently, which is
  exactly how `ev.py` was wrong for three days.
- **REFUSED is deliberately not UNRESOLVED**, and demo is why: its seeded
  history has no quotes to join, so a caller reading the cluster count off a
  refused report would publish **`G = 420`** on the public screen — a larger
  number than the live record's 199, off a database with no signal in it.

### Measured — the Odds API spend, and it was not what NEXT.md said

**1,104 credits used, 18,896 remaining**, since the tier was bought 2026-08-09.
Seven days, ~158/day, on pace for **~24% of the 20,000 tier — not 90%.** Source:
`inspect_live_db.py credits-tail` / `credits-month` on the live box, i.e. the
provider's own `x-requests-remaining`.

The 90% figure was `ODDS_DAILY_CREDIT_BUDGET = 600` (`fly.live.toml:185`) × 31.
**A ceiling is not a spend** — see `tasks/lessons.md`; the cap is never
approached (158 against 600). The per-call cost was wrong the same way: config
arithmetic predicts 2 credits, every one of the last 111 `api_credits` rows says
**6**.

**What this does and does not settle.** It settles that the recorder is not
consuming a tier. It does not make ADR 0038's "costs nothing" true — ~24% of a
paid tier is a real bill, and **the renewal is still Joe's decision, on the
invoice.** But it is no longer an argument for stopping the recorder.

### Deployed — both instances, on Joe's explicit go

**live at machine v56, demo redeployed, both verified by probing rather than by
reading a green check.**

| check | live | demo |
|---|---|---|
| `/api/health` | 200 | 200 |
| `/api/signal` | **401** — the route exists, behind the session | 200 |
| parity with `/api/gate`, `/api/board` | identical 401 | — |
| the strip renders on Board **and** Slate | not verifiable from here | yes, in its refusal state |

Live carried the retracted 52.00% / 0.38-point copy and `Buy N` until this
deploy; both are now gone from the money instance.

**One prediction did not come true, and the honest version matters.** The demo
was expected to publish `G = 420` if a caller read the cluster count off a
refused report. On the deployed demo the registered §2 population is **empty —
0 rows** — so it refuses on P1 at 0/0, not at 420/420. The seeded history does
not reach the population at all. The refusal path protects either way, and the
guard earned its place, but "it would have shown 420" was a projection from the
seed code and not a measurement of the deployed database.

**Live will fit rather than refuse.** `clv-coverage` on the box reports 9,437
scored rows carrying CLV across 7 series, so the §2 subset is populated and `G`
is now above the 199 of 2026-08-16. **Nobody has yet seen the live strip
rendered** — it sits behind the session cookie and no agent can hold one. That
is the one unverified thing in this entry.

### Open — Joe's call

- **Rotate `ODDS_API_KEY`.** A subagent read `.env` and the plaintext key landed
  in its transcript on disk. Not the Kalshi key. By this repo's own standing
  rule that counts as compromised.

### Done — directive #2, and its premise was wrong

**The nav audit found a decision, not a defect — and then a real bug inside
it.** Committed, not yet deployed.

Directive #2 read: *"a screen that is served but unreachable is this repo's
named defect in UI form."* `Nav.tsx:8-27` says otherwise, in writing and with
reasons. **Six links is a budget**: a seventh pushes the Gate — the screen that
says whether money can move — off the row at 390px. `/builder` lost its slot
because it prices sportsbook parlays, cannot change a bet on this venue, and
for a beginner can change one in the wrong direction. `/rejections` lost its
slot on 2026-08-15 because Slate is a strict superset of it. Two recorded
trades, not two oversights.

**The bug is one layer in.** That comment says *twice* that the pages are
"still served for anyone who wants it" — and there was **no inbound link
anywhere in the application.** Not the nav, not a footer, not contextually. The
escape hatch it promised was never built, and on a phone "type the URL" is not
a route a real person takes. A served page with no link is unreachable in
practice however true it is that the server answers.

Fixed with a **footer**, not a seventh nav link — the budget argument is right
and the Gate keeps its slot. Each entry carries a one-line blurb, because a
bare link named "Builder" invites a beginner to open a parlay calculator
expecting a Kalshi feature.

**`tests/test_every_screen_is_reachable.py`** now fails if any page with a
`page.tsx` is named in neither link list, if the nav budget stops being six, or
if the footer grows larger than the nav. Observed red by deleting a footer
entry. **The remedy it does not enforce: a page worth neither slot belongs in a
delete commit, and the footer must not become the place decisions go to be
avoided.**

The lesson is the recurring one — `tasks/lessons.md`, *"a collective noun is not
a measurement"*. The directive named a set (`/rejections` and `/builder`) and
predicated a defect over all of it in one breath. Opening the file took a
minute and falsified the predicate while leaving a smaller true finding behind.

### Still undecided, do not build it

`sharp-bettor`'s cost-of-execution meter — re-pointing the Board from "is this
mispriced?" to "is this cheaper on Kalshi or at a book?". Joe's call, unmade.

---


## Still open, as of 2026-08-17

Short by design. The long-form reasoning behind each is in the archive entry
named beside it.

- **The cost-of-execution meter is Joe's call, unmade.** `sharp-bettor`'s
  proposal to re-point the Board from *"is this mispriced?"* to *"is this
  cheaper on Kalshi or at a book?"*. Do not build it before he decides. Above,
  and `archive/next-2026-08-17.md`.
- **H4 is untested**, so the 0.63-point cost headroom is an upper bound, not a
  figure. Separating "settlement is free" from "`fee_cost` is entry-only" needs
  the account balance. ADR 0027.
- **The `G = 300` look happens on its own and nothing may depend on it.** The
  recorder keeps running because it costs nothing to leave running; `beta` would
  have to move 8.3 standard errors for the verdict to be anything but NO SIGNAL.
  ADR 0038, and `archive/next-2026-08-16.md`.
- **The Odds API renewal is Joe's decision, on the invoice.** ~24% of the 20,000
  tier in seven days is a real bill even though it is not the 90% this file used
  to claim. Above.
- **`ODDS_API_KEY` rotation is open, and it is a security item.** A subagent
  read `.env` and the plaintext key landed in a transcript. Tabled by Joe, not
  closed by anyone. It was recorded above but missing from this summary list,
  which is the list a future session actually reads — the omission is the bug.

**The build checklist that used to live at the bottom of this file** — *"1.
Blocked on you"*, *"2. Fix before any real money"*, *"3. Ready to build"*, *"4.
Verified working"*, *"The honest status"* — is in
[`archive/next-2026-08-07.md`](archive/next-2026-08-07.md). It is kept whole and
it is **stale**: it states 653 passing tests and a 52.00% taker bar, both since
superseded. `tasks/todo.md` is the live build log; read that, not the archived
checklist.

---

# The session index

Every session entry ever written to this file, newest date first. Full text in
the linked archive file, unchanged.

### 2026-08-17 — [`archive/next-2026-08-17.md`](archive/next-2026-08-17.md)

- 2026-08-17 (latest) — THE PRODUCT NOW STATES WHAT ITS CONCLUSION IS WORTH
- 2026-08-17 (later) — THE SCREEN WAS A VERSION BEHIND THE RECORD
- THE HUNT IS CLOSED. ADR 0038. READ THIS FIRST.
- THE WHOLE PROP-MODEL LINE IS CLOSED. ADR 0037.
- PITCHER-K IS REFUTED. THE MODEL WORKS; THE PARAMETERS CANNOT.
- 2026-08-17 (~00:30Z) — P1 WAS READING THE WRONG STATISTIC. NFL IS A SKIP. MLB PROPS REORDER TO PITCHER-K.

### 2026-08-16 — [`archive/next-2026-08-16.md`](archive/next-2026-08-16.md)

- 2026-08-16 (~22:40Z) — BETA IS MEASURED AND NEGATIVE. WE ARE OFF THE GATE. BUILD AN OPINION.
- 2026-08-16 (~21:05Z) — LIVE WENT DOWN FOR 54 MIN (VOLUME FULL). FIXED. AND THE FEE IS 2x TOO HIGH.
- 2026-08-16 (~19:20Z) — ⚠ `actionable` IS NO LONGER 0. AUDIT IT BEFORE ANYTHING ELSE.
- 2026-08-16 (~19:30Z) — PROPS ARE OFF THE SCHEDULE. THE FUNNEL IS SPEC'D. ONE DUMP STILL NEEDS A LAPTOP.
- 2026-08-16 (~18:20Z) — THE REFRESH IS DEPLOYED AND FIRING. TWO THINGS STILL NEED JOE'S HANDS.
- 2026-08-16 (~06:30Z) — THE TWO TOP ITEMS ARE UNCHANGED AND STILL WAIT ON THE 16:51Z SLATE
- 2026-08-16 (~03:00Z) — A DEPLOY IS OWED, AND ONE MEASUREMENT IS STILL DUE AT ~17:30Z
- THE CREDIT DEFECT IS FIXED IN THE REPO AND **NOT YET DEPLOYED**. Deploy is the first thing. *(SUPERSEDED: it was deployed and verified ~00:35Z.)*

### 2026-08-15 — [`archive/next-2026-08-15.md`](archive/next-2026-08-15.md)

- PROPS ARE RECORDING ON LIVE. One defect fixed, **one still open and it has a clock**. *(SUPERSEDED by the section above: the credit defect is fixed in the repo, pending deploy.)*
- PROPS ARE BUILT, ALL FOUR SLICES. **SUPERSEDED by the section above — they are now deployed and two defects were found in the first live pass.** Note its credit figures are the ones that turned out wrong.

### 2026-08-14 — [`archive/next-2026-08-14.md`](archive/next-2026-08-14.md)

- PROPS THROUGH THE EXISTING PIPELINE. **SUPERSEDED — all four slices are done; see the section above.** Kept for the constraints it records.
- PROPS ARE CHARGED THE BASEBALL RATE. H-SPORT survived a real falsification test.
- PROPS ARE REACHABLE, AND THE FEE COEFFICIENT IS THE GATE, NOT THE MARKET
- THE FEE HEDGE IS RETIRED. The break-even bar is 51.75%, and one published analysis is now stale.
- ROUND THREE IS RUN. The fee is NOT a venue constant, and the code is wrong on baseball.

### 2026-08-13 — [`archive/next-2026-08-13.md`](archive/next-2026-08-13.md)

- Q-W RAN AND ACTIVATED. Nothing is blocking the orders but Joe's clock.
- Q-W IS BUILT AND COMMITTED (superseded above; kept for the image finding)

### 2026-08-12 — [`archive/next-2026-08-12.md`](archive/next-2026-08-12.md)

- ADR 0020 IS WRITTEN. The reserved number is spent, and it opens nothing.

### 2026-08-11 — [`archive/next-2026-08-11.md`](archive/next-2026-08-11.md)

- THE CEILING ON RELAXING `stale_odds` IS 23 ROWS = 14 OPPORTUNITIES, AND NOTHING BEHIND IT IS A RUNWAY
- OPEN QUESTION FOR JOE: 85.8% of the $3.66 lands in a series with zero rows in the record
- ADR 0025: the `stale_odds` claim was OVERSTATED by ~10x, and its mechanism ran backwards
- ⏱ Time-sensitive, and it is free
- RESOLVED: `capture_odds_repeat_poll.py`'s P1 could not fail. Fixed at `39628e0`.
- The demo instance renders a healthy version of the screen that is empty on live

### 2026-08-10 — [`archive/next-2026-08-10.md`](archive/next-2026-08-10.md)

- `inspect_live_db.py` RUNS NOW, and answers ONE of the four questions it was queued for
- ADR 0021 §7: the dump is refused for the CLV test, and NOT ruled on for the other one
- CORRECTED: ADR 0021 §7.2 asserted something its own source had already refuted
- 2026-08-10 22:34:21Z — THE SWEEP SERVED. The latch is refuted, F4's prediction held.
- RESOLVED: the 21.5-hour odds gap had an empty denominator
- The documented phone health check cannot pass, and never could
- 2026-08-10, overnight — SIX DURABLE FACTS FROM TONIGHT'S LANES
- ⏱ 2026-08-10, evening — RUN THIS FIRST, THEN READ THE REST
- 2026-08-10, overnight — THE REFUTATION IS WRITTEN, AND IT QUOTES A FIXTURE AS A FACT
- ⚠ 2026-08-10 — READ THIS IF YOU ARE A PARALLEL SESSION
- 2026-08-10, end of session — ADR 0019 LANDED, AND THE REPORTED BUG WAS WRONG
- INFRASTRUCTURE INTERRUPT: Actions minutes, and the public flip
- 2026-08-10, end of session — THE BOUND FAILED, AND IT FOUND A REAL BUG
- 2026-08-10, mid-session — JOE: ONE COMMAND (still true; the ADR framing above supersedes)
- THE PLAN: one joint bound, then stop and write the refutation
- the edge test is REGISTERED, and it retracts a claim of mine
- `partner` re-triaged: calibration is the CONTROL for the edge test
- the power-ratings finding is AUDITED, and `no_edge` may be misnamed
- DEPLOYED, D1 is answered, and deploys are now BATCHED
- 2026-08-10, earlier — LIVE READ ACCESS IS UNBLOCKED
- half the documented strategy has never run, and the $5 buys a field name

### 2026-08-09 — [`archive/next-2026-08-09.md`](archive/next-2026-08-09.md)

- 2026-08-09, ~22:40Z — DEPLOYED, and `actionable` has been 0 for the whole record
- 2026-08-09, late — six lanes landed, and three audits refuted the prose over them
- 2026-08-09, ~19:30Z — the bankroll trap is fixed; the backfill cannot open the gate
- CLOSED 2026-08-09 — the 94% is withdrawn, and the replacement died too
- 2026-08-09, ~16:00Z — the gate freeze was an empty slate. DECIDED: accept.
- 2026-08-09, 06:00–09:00Z — five items closed, and one of them was Joe's
- DEPLOYED (2026-08-09, 05:36Z) — the budget stopped being the constraint
- Superseded (2026-08-09) — the 20K tier is bought; the key is not installed
- The gate is blocked by the odds budget, and the guards are fine
- READ FIRST (2026-08-09, later) — the log stream drops lines, and the number everyone quoted was a 10% sample
- READ FIRST (2026-08-09) — the gate's counter cannot grow, and it is arithmetic
- DEPLOYED (2026-08-09, ~03:17Z) — and `clv_scored` left zero
- HANDOFF (2026-08-09, ~00:10Z — the settlement path is built, nothing is deployed)

### 2026-08-08 — [`archive/next-2026-08-08.md`](archive/next-2026-08-08.md)

- HANDOFF (2026-08-08, evening — demo is deployed, live is one tap away)
- HANDOFF (2026-08-08, 14:4xZ — the sheet is merged, and running it found four more)
- HANDOFF (2026-08-08, overnight — three lanes, and CI was already red)
- HANDOFF (2026-08-08, 05:2xZ — deployed, and the demo found the bug for us)
- Joe's asks, 2026-08-08 — four of them; two are done
- HANDOFF (2026-08-08, later still — the price is live, and a review caught me)
- HANDOFF (2026-08-08, earlier — the 30-second window is fixed)
- HANDOFF (2026-08-08, earlier)

### 2026-08-07 — [`archive/next-2026-08-07.md`](archive/next-2026-08-07.md)

- 1. Blocked on you
- 1b. Found by deploying live
- 2. Fix before any real money
- 3. Ready to build (no blockers)
- 4. Verified working
- The honest status
