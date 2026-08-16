# Start prompt — paste this to open the next session

Rewritten **2026-08-16 ~02:30Z**. The session that **shipped Willy Balters and
the crew avatars, registered the one-sided prop recovery and built its
instrument, and refuted the plan to halve the prop bill by finding Pinnacle in
the EU half.**

Say *"read start.md and follow it"*, or paste this whole file.

---

Read `CLAUDE.md`, `tasks/NEXT.md` and `tasks/lessons.md`. NEXT.md is the
actionable checklist and **its top supersedes everything here**.

## ⏱ FIRST — two things, and both are waiting on ONE slate

**Everything is deployed and verified. Nothing is broken.** The live planner
holds a slot at **16:51Z–17:21Z covering 13 games**. Both open items need it to
fire first. Check the clock before doing anything: `date -u`.

### 1. The credit number, due ~17:30Z

That firing should cost **6 + 20×13 = 266** credits of 400.

```
flyctl ssh console -a kalshi-cockpit \
  -C "python /app/scripts/inspect_live_db.py credits-day --date 20260816"
```

- **~266** → the fix held. **Write that number into `.env.example` and
  `runner.py:1529-1535`**, which deliberately carry no per-slate figure right
  now. Reconcile it against the provider's own `x-requests-used`
  (`BudgetState.drift`) before publishing it — a cost derived from an assumed
  input is the assumption restated, which is how the last figure was wrong.
- **~390+** → the fix did not hold. Read `sweep-log` and start there.

`credits-day` **requires** `--date YYYYMMDD` and refuses to guess. The budget day
runs 10:00Z→10:00Z, so a sweep at 17:00Z on the 16th is `--date 20260816`.

### 2. The prop-rungs dump, and it is a ONE-SHOT

```
flyctl ssh console -a kalshi-cockpit \
  -C "python /app/scripts/inspect_live_db.py prop-rungs --json --limit 20000" > dump.json
.venv\Scripts\python.exe scripts/analyze_prop_onesided.py dump.json
```

**Take it after the slate, not before.** As of 02:22Z the record holds **7**
prop fixtures from a single sweep at **2026-08-15 19:41:53Z**; the slot covers
13. §9 of the registration allows **one run**, and an `n < 30` UNRESOLVED would
burn it on a thin record for nothing.

**Run the registered analyzer on that dump BEFORE reading the dump for anything
else** — including the Pinnacle question below. The rules are committed and
pushed (`400d712`), so they cannot move; running the scorer first preserves the
ordering guarantee rather than relying on that.

## WHAT SHIPPED, AND WHAT IT DOES NOT CLAIM

Six commits, all pushed, `origin/main` at **`104dab6`**. **2,730 tests pass, 10
`xfail(strict=True)`, ruff clean, `npm run build` clean.** Verified at the time
of writing, not inherited — **re-verify before trusting it:**

```
git log --oneline -7
git rev-list --count origin/main..HEAD
git status --short
.venv\Scripts\python.exe -m pytest -q
```

Live was deployed and verified this session (run `31921306708`,
`instance_mode: live`). Two commits landed **after** that deploy — `7718657`
and `837b40d` — and both are **docstrings and tests only**. No behavioural
drift, no redeploy owed.

### `837b40d` — props are **NOT** unanchored, and the probe that said so never asked

**Read this one first. It reverses a planned optimisation and corrects a claim
that was in production code.**

`prop-bookmakers` returns **ten** books quoting MLB props, and one is
**`pinnacle`** — 406 quotes, 7 events, 3 market keys on one sweep. `pinnacle`
is in `SHARP_BOOKS`, and The Odds API serves it under **`eu` only**.

`runner.py` had said the opposite as a statement of fact: *"none of them is
Pinnacle or Betfair, so `anchored_on_sharp` is 0 on every row here by
construction."* The chain, verified end to end:

```
scripts/probe_prop_dispersion.py:149   sends `"regions": "us"`
The Odds API                           serves `pinnacle` under `eu` ONLY
.env.example / deployed instance       runs `ODDS_REGIONS=us,eu`
```

A true statement about a us-only laptop pull was quoted into production as a
property of a system that asks a wider question.

**The `eu` half of the prop call is buying the only sharp book on the prop
record.** The plan two handoffs carried — drop `eu`, halve the 20-credit prop
event — would have deleted it. **The saving does not exist. Closed.**

**⚠ Do not now write the opposite either.** `consensus_devig` anchors only where
the sharp book is in `quotes_by_book` for that rung, and `prop_quotes_for_event`
admits a book only when it quotes **both** sides. Pinnacle covers 3 of 10 market
keys. **Its two-sidedness on prop rungs is UNMEASURED.** Neither "props are
anchored" nor "props are unanchored" may be written until `prop-rungs` has run.

**And if it turns out to be two-sided somewhere, read the consequence before
celebrating it:** `consensus_devig` does `selected = sharp or usable`, so such a
rung's consensus becomes **Pinnacle alone**, the other nine books are discarded,
and `market_width` goes `None`. That is a *different* row, not a better one.

### `400d712` — the one-sided prop recovery, registered before the data

`docs/measurements/2026-08-16-preregistration-prop-onesided-recovery.md`.
**Changes no money path.** `prop_quotes_for_event` drops every one-sided book —
174 of 222 matched keys on 2026-08-14, because the `_alternate` feeds are mostly
Over-only.

**The registration's own suspicion is of the "4.6×".** That is dropped keys over
kept keys, **not recoverable over kept** — a one-sided alternate rung is only
recoverable if the same book quotes a two-sided **primary** for that player and
market, and nobody has counted how often that holds. **Gate A counts it first
and can kill the change on size alone, before any accuracy number is read.**
**Do not quote 4.6× as the prize again.**

Two artefacts. `prop-rungs` on `inspect_live_db.py` emits **rows, not a
verdict** — that script is explicitly not a measurement harness, and
`price_decimal <= 1.0` is deliberately **not** filtered because an exclusion the
registration requires to be *counted* cannot be counted by something that never
emits it. `scripts/analyze_prop_onesided.py` holds every registered constant,
is a laptop Tool, and **refuses a truncated dump** rather than scoring the
alphabetical front of the record.

The end-to-end smoke run caught a real defect **before any data**: the Level-2
grouping key omitted the player, so four players devigged into one book-set —
the exact failure `prop_quotes_for_event`'s docstring warns about. A margin
sweep then confirmed the bars bite where registered and in the predicted
direction (a book shading alternates 1 point harder gives `+0.587pt` → REFUSE).

### `b0c2fab` — Willy Balters, and the crew have faces

Joe: *"all I see is the Skeptic and he denies everything."* A real gap: the row
already carried the book distribution and nobody spoke for it.

**Willy Balters is a fiction with a fiction's name**, which is Joe's own fix and
the only reason the character can exist — `.claude/agents/sharp-bettor.md`
forbids inventing words for a living person.

**One voice, one data source, structurally.** Willy is handed a
`BookDistribution` and **never sees the row**, so drift, volume and edge are
unreachable rather than merely unused. No line can weigh two factors, so no line
can become a rating. `tests/test_crew_bubble.py` pins it; 11 mutations run.

Avatars are **inline SVG in `currentColor`** — no asset pipeline, no remote
fetch from a page showing what somebody is about to bet. **Joe called the style
a placeholder and will revisit it.**

### `7718657` — a laptop Tool must not reach the money box

Two registrations said in prose that their analysis script must stay out of the
image and nothing checked either. Both were excluded only *incidentally*, by
never having been allowlisted.

## JOE'S QUESTIONS THIS SESSION, ANSWERED

**"Can't the Skeptic and Scout be personas written in code, not agents?"**
**In the UI they already are, and always were.** Every line in `CrewBubble.tsx`
is a pure function of the row: no network, no model, no spend, nothing on the
Kalshi box. The `backend/agents/` modules of the same names are a different
thing — they cost money because they **fetch facts the record does not hold**.
**A code persona can voice any fact already on the row, forever, for nothing. It
cannot produce a new one.** That is why the Scout's line is still an admission.

**"What if we reduce the Scout to professional sports and not everything?"**
**Scope is not the lever and narrowing it saves nothing.** The Scout is already
sports-only *and* game-scoped, and the tool prices only `KXMLBGAME` and
`KXWNBAGAME` — both professional. There is no non-professional work to remove.
**Calls per day is the lever.** `$0.35–$2.01` a saturated day is 24 calls at the
deployed ceiling on `.env.example`'s **[ASSUMED, uncited]** price, so ~$0.015–
$0.084 a call — and that per-call figure inherits the assumption. An
**on-demand trigger** (Scout runs when Joe taps a row) takes a real night to 2–3
calls, **~$0.05–$0.25 a day**. Second lever: `WEB_SEARCH_TOOL["max_uses"]` is
**6**; 2–3 cuts the largest per-call term.

That does not unblock it. Wiring Scout still turns two tests red, and
`BILLED_PATH_CALL_SITES` **cannot be satisfied by editing a list** — it needs a
**batch budget** like `review_surfaced`'s, because the meter is per-caller by
design. Plus an ADR citing 0022. **Still tabled by Joe. Do not start it unasked.**

## THE THREE THINGS THAT DECIDE THIS PROJECT

Joe said on 2026-08-11: *"You seem to do so much testing instead of building."*
**Keep this at the top of every handoff until it stops being true.**

| # | Question | State |
|---|---|---|
| 1 | **Is the staleness guard wrong?** | **ANSWERED 2026-08-11, opens no runway.** ADR 0020 / 0025. |
| 2 | **Is the fee coefficient 0.070 or 0.035?** At 0.035 the taker bar drops to **50.88%**. | **THE ONLY LIVE QUESTION.** Needs a second MLB window **on or after ~2026-09-04** and **one 1-contract fill**. Nine baseball fills pin `k` to `(0.03497, 0.03501]`. |
| 3 | **Is Kalshi simply the sharp side?** | **DEAD on power (2026-08-11).** The Slate's book column looks at it per row; it is a display, not a test. |

**ADR 0023 expires 2026-08-31 (UTC) with default A** — 15 days. Nothing this
session moved item 2, and nothing may be written up as though it did.

## WHAT IS LEFT, IN ORDER

1. **The credit number**, then **the prop-rungs dump**. Both at the top.
2. **Score the first prop rows on CLV** once a slate settles. **Register the
   measurement before looking.** Props are baseball, charged `k = 0.035`, priced
   at 0.070 — understated by up to 2× on the fee component, deliberately.
3. **The settlement `fee_cost` capture** for the five round-three positions —
   the only direct test of **H4**, which the 0.63-point headroom rests on.
   Fills endpoint retention ~3 months from 2026-08-14.
4. **The Scout — TABLED BY JOE. Do not start it unasked.** The cost answer above
   is recorded so nobody re-derives it.

## GOVERNANCE — Joe's ruling, not a convention you may relax

`flyctl ssh console` against `kalshi-cockpit` may **only invoke a committed,
reviewed script by path.** No inline code, no `python -c`, no base64, no
filesystem browsing, no interactive session. **The allowlist does not enforce
this** — a permission pattern matches a command prefix and cannot see inside
`-C "..."`. Five sessions have now written this rule and two drifted from it
within the hour. Assume you will too.

**Three of forty-eight `scripts/*.py` are in the image**, and `.dockerignore`
decides, not `Dockerfile` — `run_loop.py`, `migrate_db.py`, `inspect_live_db.py`.
*(48 counted 2026-08-16 with `.dockerignore`'s own matcher, not carried forward.
**Count it; do not copy it.**)* `analyze_prop_onesided.py` and
`census_non_sports_spread.py` are laptop `Tool`s, must not ship, and
`tests/test_has_callers.py` now asserts that rather than leaving it incidental.

`inspect_live_db.py` query names: `sweep-log`, `credits-tail`,
`credits-day --date YYYYMMDD`, `credits-month`, `series`, `kalshi-quotes-band`,
`prop-bookmakers`, and **`prop-rungs`** (new this session; takes
`--odds-event-id` and honours `--limit`).

**`flyctl ssh console` is sometimes refused by this environment's permission
classifier** — not by the governance rule, which those commands satisfy. It
worked on the second attempt this session. If it is refused, ask Joe to run it
with a leading `!` rather than working around it.

**Deploying is a phone button:**

```
gh workflow run deploy.yml -f instance=demo
gh workflow run deploy.yml -f instance=live -f confirm_live=kalshi-cockpit
```

The typed confirmation is the guard against a mis-tap; it is not optional.

**Ask before money or a deploy. Do not ask permission to continue** — Joe leaves
8-hour unattended stretches. **Every push publishes to the world immediately.**

## SETTLED — do not re-derive or re-propose

- **One signal, not two.** `elo.py` has no production caller. **Do NOT wire it up.**
- **The `eu` region stays on the prop call.** It buys Pinnacle. Re-opening this
  means paying for the sharp book's absence.
- **Props may not be described as anchored OR unanchored** until `prop-rungs`
  measures Pinnacle's two-sidedness.
- **The non-sports direction is closed on cost.** Run 2 is the run. **Do not
  re-run it for a better number.**
- **Nothing on the Slate may become a composite.** No score, no rating, no
  weighted confidence. Four tests enforce it now — two on the payload
  (`test_slate.py`, `test_api.py`) and two on the crew (`test_crew_bubble.py`).
- **The desk personas are code and stay code.** Voicing a row costs nothing;
  fetching a new fact is what costs money.
- **ADR 0025** — the `stale_odds` re-opening is refused. 23 rows / 9 clusters.
  **Never write "844 of 935" as rows in play.**
- **`ALL_CHECK_NAMES` has 12 entries, not 14.**
- **`TAKER_COEFFICIENT` stays at 0.070** until item 2 resolves. `core/fees.py` is
  untouched by everything above and must stay that way.
- **The coefficient is not one number across the record** — baseball 0.035,
  WNBA/ATP/PGA 0.070. **Never write "the fee is 0.035".**
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
- **`AGENTS.md` is a nine-line pointer to `CLAUDE.md` and must stay one.**

## TRAPS

- **`start.md` is a snapshot; `git log` is the record.**
- **A probe's request parameters are part of its finding and do not travel with
  the sentence.** "No sharp book quotes props" and "no sharp book appeared in a
  us-only pull" are the same sentence minus four words, and the four words are
  the entire content. **"X is absent" is only ever as strong as the query that
  looked for X** — absence is the one finding a narrowed input reproduces
  perfectly and silently. Before quoting a measurement into production code,
  **re-read the request it made, not the paragraph about what it found.**
- **A source-text test can pass on its own explanation.** Three assertions in
  `test_crew_bubble.py` failed on the docstrings that justified them, and a
  fourth passed with the code deleted because the comment held the words. Grep
  comment-stripped source, and **run the mutations** — that fourth one was found
  no other way.
- **A ratio against a control assumes the control is one number.**
- **"Unreadable" and "empty" are decided by the wire, not by your rule.**
- **A cost model that prices one call but not the call it triggers will
  authorise a 6-credit request that spends 266.**
- **A guard copied from a neighbouring path inherits its assumptions, not its
  safety.**
- **A raise inside a per-item loop nested in a per-slate loop fails the slate.**
- **A fixture that always starts from empty cannot test teardown.**
- **A subagent's confident claim is the one to re-run yourself.** `partner` cited
  `tasks/prior-art.md:44-46` for an RFQ census. **That file does not exist.**
- **`git checkout -- <file>` reverts the whole file, not your last edit.** It
  destroyed an hour-old unstaged query this session while backing out a
  mutation. Keep an off-tree copy, or mutate through a script with a `finally`.
- **`git add tasks/next.md` matches nothing and says nothing.** Git tracks
  `NEXT.md`. **Run `git status --short` after any hand-typed `git add`.**
- **`docs/measurements/data/` is gitignored.**
- **A placeholder drawn from the production namespace is a prediction.**
- **`flyctl logs` is lossy** — ~90% of a burst is dropped.
- **`flyctl ssh console` prints `Error: The handle is invalid` on Windows after
  a successful query.** It is terminal teardown, not a failure. Read the output
  above it.
- **A background job reported stopped may still be running.** Check `ps`.
- **Two lanes in one working tree fight over git. Add by explicit path, never
  `git add -A`.**
- **A status word in a handoff may be a human's summary, not an instrument's
  output.** Grep the named instrument for the literal token.

## Standing instructions from Joe

1. **Call `partner` first** and let it set the queue. **Delegation is its call.**
   Its output is **not** exempt from the fabrication trap above.
2. **Parallelise by default — two concurrent lanes, never more.**
3. **`measurement-skeptic` audits anything before it enters the record**,
   especially good news, and especially a kill.
4. **Deploys are batched and Joe runs them.**
5. **Don't ask permission to continue. Do ask before money or a deploy.**
6. **Say unprompted when the session should end.** Target 300–500K tokens.
7. **Watch the build-to-measure ratio and say so when it is wrong.**
