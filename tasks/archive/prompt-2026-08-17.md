# Next session prompt

Paste everything below the line into a fresh session.

---

Read `tasks/NEXT.md` (top entry only), `tasks/lessons.md` (top four entries)
and `CLAUDE.md`. All are readable — 50KB / 42KB / small.

STATE
`main` at `be3040f`, schema v9. 3,100 tests pass, 10 xfailed, ruff clean,
`tsc --noEmit` clean. Re-verify; do not inherit.

BOTH INSTANCES ARE DEPLOYED AT `679e1b9` AND THAT IS NOT A BUG. The four
commits after it are docs only. Check `/api/health` before reacting to a
deployed-sha-behind-HEAD reading — it now carries `git_sha`.

THE HUNT IS STILL CLOSED. ADR 0038. Nothing below reopens it, and nothing
below is a search for an edge.

READ THIS BEFORE PLANNING: THERE IS NOT A SESSION'S WORK HERE

`partner` was asked at the end of last session what was next and answered
**stop**, for the second session running, and again declined to name a sixth
item. That was said *after* it had watched four of its own items get
discharged, and after two of its own claims were checked and found wrong. It is
a considered answer, not fatigue.

**Do not convert the items below into a lane to give yourself something to do.**
That failure has a name in this repo and it happened last session: an entire
work item was scoped from a guard that turned out to be structurally
unreachable, and the tell was that nobody had checked what reached the
component. See `tasks/lessons.md`, top entries.

The honest shape of this session is: **one ten-minute measurement, then a
decision by Joe about whether anything else is worth funding.**

1. THE ONLY THING THAT IS ACTUALLY DUE — ~10 MINUTES

The budget day closed at **2026-08-18T10:00:00Z**. That is the first *full* day
under the current configuration and therefore the first honest daily spend
figure this project has ever had.

```
flyctl ssh console -a kalshi-cockpit -C "python /app/scripts/inspect_live_db.py credits-day --date 20260817"
```

Read-only, `mode=ro`. `--day-start-hour` defaults to the real 10:00Z boundary;
**do not re-bucket by calendar date** — that error moved the two decisive days
by up to 40 credits last session.

WHAT IS ALREADY KNOWN, so you are not re-deriving it:

- **A sweep now costs 2 credits, not 6.** Measured 2026-08-17T20:56:15Z and
  confirmed three ways: the row carries `markets = h2h` directly, our recorded
  `cost` is 2, and **the provider's own counter moved by exactly 2**. The last
  three-market call ever recorded is 2026-08-16T22:59:23Z.
- **Scheduled props are off** (ADR 0032) — no 20-credit calls.
- **Every row before 2026-08-17T20:56Z describes a configuration that no longer
  runs.** Any run rate computed from them is void, including the "158/day" in
  the archive and the "412/day" that was retracted.
- **The tier cannot be exhausted before 2026-09-17** at the deployed 600/day
  ceiling. That claim needs no run rate and no renewal date.
- **The renewal date is recorded nowhere.** It is measurable, not guessable:
  `remaining_reported` jumps back to 20,000 on the first call after the cycle
  rolls.
- There was a **~31 minute outage on 2026-08-17 (21:06–21:27Z)** during the key
  rotation. It suppresses that day's total slightly. **Say so** rather than
  quoting the number clean.

`docs/measurements/2026-08-17-odds-credit-run-rate.md` is the write-up; add the
day figure to it. Registered-measurement rules do not apply — this is a
descriptive read of rows that exist, not a hypothesis test. **Run it past
`measurement-skeptic` anyway before it enters the record.** It killed the last
draft of this exact document and was right on every count.

The decision — whether the tier is worth renewing — is **Joe's, on the
invoice.** Give him the run rate, the projection, and what the recorder buys
for it, stated so it fits on a phone.

2. TWO DEFECTS FOUND WHILE VERIFYING THE ROTATION. REAL, SMALL, NEITHER FIXED

Both were observed on the live box, not reasoned about. Neither is urgent and
**neither is a reason to open a session on its own** — do them only if Joe wants
the session to continue past item 1.

- **A failed odds call resets the freshness clock.** Immediately after the 401
  the scheduler reported *"odds are 0.4min old"* and deferred its retry a full
  ten minutes. **A rejected key makes the system believe it holds fresh odds** —
  an outage presenting as freshness, which is the dangerous direction. Wants a
  guard observed red first.
- **A restart mid-window costs up to 15 minutes of blindness.**
  `backend/scheduler.py:182` returns
  `fast_interval_s if self.window_open else self.slow_interval_s`, and a fresh
  process starts with `window_open` false — so the loop slept **900s** inside an
  open window. It looks exactly like a hung process and cost real diagnosis time.

3. THE ONE HONEST CANDIDATE, AND IT IS JOE'S CALL WHETHER IT IS WORTH A SESSION

`partner` named this unprompted and explicitly **not** as work, **not** as a
hunting line: the only stated purpose in `CLAUDE.md` with no execution behind it
is that this become a **public portfolio repo**. It already *is* public. Whether
the record reads as *"we asked, we found out, and here is how"* rather than as
an abandoned trading bot is a real question with a real answer, and it is
exactly the kind of thing nothing fails for skipping.

It needs a **different reviewer** than any on last session's list. Do not start
it without Joe saying yes.

DO NOT PICK THESE UP — the drop list, and it is a drop list, not a backlog

- **Turning scheduled props back on.** ADR 0032 stands; its 2026-08-17
  annotation explains why the sourcing error does not reverse it.
- **The ~99 clusters to `G = 300`.** Waiting is not work. **Do not schedule a
  session for it.** When it crosses, read `tasks/NEXT.md`'s top entry first —
  the intake changed composition on 2026-08-16 and the pooled estimate is
  expected to drift **toward good news for a reason that is not evidence**.
- **The blank gap between the last Board card and the footer.** Cosmetic,
  undiagnosed, on a hard-closed line.
- **Exercising the manual-refresh path.** It spends credits and the tap has now
  never fired in 113 rows of life.
- **The sweep banner.** Closed permanently.
- **Anything reopening the hunt.** A proposal must name which quadrant row of
  ADR 0038 it overturns, and with what measurement.
- **A per-contract cost line on the Board.** Dead twice over: the guard it was
  meant to defeat never fires, and the fee curve is flat at 1.7–1.8c across
  every price that trades, so it cannot rank anything. `sharp-bettor` argues a
  comparator belongs on the **ticket sheet** at commitment — **verify it is not
  already displayed** before anyone builds that.

CONSTRAINTS — all still in force

Run `runtime-realist` BEFORE briefing agents or quoting an operational number.
Name the file that would change if the deploy changed — never `.env.example`,
never a code default, never a docstring.

**A ceiling is not a spend, and a formula is not one either.** Cite the row that
recorded it (`api_credits`, `odds_sweep_log`, the provider header).

**Open the set before predicating over it — and check the claims that create
work as hard as the ones that flatter you.** Last session the flattering number
got verified and the two that would have spent a session did not; both were
wrong. A claim that something is broken buys its author a task, and that is a
motive too.

**Grep for callers before believing a feature exists — and before believing a
guard hides anything.** Both directions are now proven wrong in this repo.

**Any source scan must strip comments.** These files are more prose than code;
a scan that does not will read the documentation, produce false positives
against correct code, and silently absorb your own mutations so a real guard
reports itself as decoration.

**Verify a guard by disabling it and watching it fail — and check that the
mutation landed where the guard actually looks.**

Registered measurement first if anything is measured. Money-touching actions
need Joe's say-so; deploys go through `deploy.yml`, and `gh workflow run` is a
classifier coin-flip, so retry rather than handing it back. Check `gh`'s exit
code, not a piped tail's. **Put long commit messages in a file and use
`git commit -F`** — backticks and quotes in `-m` get shell-interpreted, which
happened twice last session.

If Joe is at a laptop with Chrome open, **say so and look yourself** rather than
asking him to check a screen.

**Do not poll the live box on a tight loop.** A 45-second `flyctl ssh` watcher
floods the machine's logs with SSH session lines and buries the runner output
you are trying to read. Space checks to the cadence of the thing you are
waiting for.

SESSION SHAPE

Item 1 is ten minutes. Ask Joe whether he wants anything after it. **If he does
not, say so plainly and stop** — that is the correct outcome here, and it has
been the correct outcome twice already.
