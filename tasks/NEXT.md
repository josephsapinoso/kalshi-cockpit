# Next — your checklist

**How this file works.** This file holds the **current state**: the latest
session entry, plus what is still open. Every earlier session entry is in
`tasks/archive/next-YYYY-MM-DD.md`, **verbatim** — the archive reconstructs
the pre-split file byte for byte. The index at the bottom lists every entry
and which file it is in.

**Split at ~90% of 262,144 bytes, and read `wc -c` BEFORE writing an entry,**
**not after.** `tests/test_session_files_are_readable.py` guards the file; what
breaks first is the instruction to read it, because a session that cannot
read the whole file reads the head and silently believes it has the state.
Cut on a date boundary, name the archive for the split date, move the index
lines in the same edit (a split without them is a data loss with a table of
contents), and verify by md5. The seven splits so far and what each taught:
`tasks/archive/next-split-log.md`.

---

## SESSION START — if Joe said "read NEXT.md", this box is your prompt

Repo: `C:\Users\josep\Documents\Claude\Projects\kalshi_betting_tool`,
branch `main`. Check `git status` and `git log origin/main..main` rather than
trusting any sentence here, and read the LIVE instance's `/api/health` for its
`git_sha` — it sits under `build`, not at the top level. The calibration study
is STOPPED (2026-08-20, Amendment 2; the recorder machinery still runs). Joe is
a beginner and has asked to be educated: define every betting/stats term at
first use, via `frontend/src/lib/glossary.ts` and `<Term>`.

**The test count is CI's, not a hand-collected number.** `.github/workflows/ci.yml`
runs `ruff check .` and `python -m pytest -q` on every push, under a 15-minute
cap. Read the last green run: `gh run list --limit 5`. Run targeted tests
locally while you work; let CI collect the total. If you must take a count, do
not reconcile a baseline by reasoning about a delta — collect both trees. The
suite is ~15-22 minutes and growing with the record; a slow run is not a hung
one.

**READ THE DEPENDENCY ALERTS AT SESSION START — new 2026-09-09, ADR 0117.**
They were on none of the three queues, and two critical unauthenticated RCEs
sat on the public money box until a routine push happened to trigger a rescan:

    gh api repos/josephsapinoso/kalshi-cockpit/dependabot/alerts?state=open \
      --jq '.[] | [.number,.security_advisory.severity,.dependency.package.name] | @tsv'

**Do not read the alert summary git prints on push.** It is a snapshot taken
*before* the rescan that push triggers, so it describes the previous state.
Mine said "1 high" while the truth a second later was two criticals and a
high. And **do not trust an alert's own `state`**: alert #15 reports `fixed`
while `requirements.txt:9` still pins a version inside its vulnerable range,
because GitHub's dependency graph lost the package's resolved version.
**This query is therefore known-incomplete — it cannot see `cryptography` at
all.** Verify a fix by reading the version out of the running container, and
see open item 3 below.

**Two things to know before planning. CLAUDE.md is current on both:**

1. **The signal test has NOT declared.** The verdict is UNRESOLVED at
   `G = 216`, the floor is 713, the look is not coming, and every interval sits
   entirely below the 0.40 threshold — settled negative for planning.
2. **What the tool is FOR is settled — ADR 0071.** A personal betting desk
   first; price transparency as the job; a gap you may show on a row and
   never rank by; sharing means someone runs their own copy. Do not re-derive
   the purpose.

**Other lanes may be running; main is not the whole picture.** Read the
generated board, never a hand-typed lane table:

    git worktree list
    .venv\Scripts\python.exe scripts/lane_board.py

It reads every worktree and local branch — ahead/behind, uncommitted work, ADR
and schema claims, overlapping hunks. `tasks/LANES.md` carries the last written
snapshot plus the **allocation ledger**: what a live lane has said it will take
before it exists on disk. **Do not claim an ADR number or schema version by
reading either one** — write `docs/adr/DRAFT-<slug>.md` with no ordinal and
take the number in the merge commit after `git fetch`; the guard refuses a
`DRAFT-` file on `main`. Full rule: `docs/adr/README.md`. `docs/adr/0006-*`
sharing a number is deliberate, not a collision.

**The UI decisions live on GitHub, not here.** Map issue **#3 "Cockpit for the
pilot"** on `josephsapinoso/kalshi-cockpit` holds every screen decision Joe has
made, with evidence; a session that plans UI from this file alone will
re-derive them. Read the map body, then the frontier (open, unblocked `0`,
unassigned `-`, first in map order wins):

    gh issue view 3 --json body --jq .body
    gh api repos/josephsapinoso/kalshi-cockpit/issues/3/sub_issues --paginate \
      --jq '.[] | select(.state=="open") | [.number,(.assignee.login // "-"),(.issue_dependencies_summary.blocked_by // 0),.title] | @tsv'

Conventions: `docs/agents/issue-tracker.md`. Claim a ticket by assigning it to
yourself before any work; resolve one per session. The map produces
*decisions*, not builds. **The `/wayfinder` skill that drew the map is not
installed in this plugin version** — nothing can invoke it, and the map is
read with `gh` only.

**THIS FILE IS THE FRONT DOOR — Joe's answer, 2026-08-28.** Three queues: this
file's Open list (repo and infrastructure work), the map's open tickets
(decisions to make), and **decided-not-yet-built** — a closed ticket carrying a
spec is a NEXT.md item, and it belongs to nobody unless it is written here.
Read `git status`, then the Open list in the latest entry, then the frontier
query, in that order.

**THEN INVOKE THE `partner` AGENT, BEFORE PLANNING ANYTHING** — CLAUDE.md
workflow step 0. Hand it the state (what is open, what landed, what is blocked)
and ask for a ranked list AND which items can run as parallel lanes. Skip it
only for a single errand Joe named himself.

Read `CLAUDE.md`, then the latest entry below (it is the whole brief), then
`tasks/lessons.md` top two. Re-verify state, never inherit it:

    .venv\Scripts\python.exe -m pytest -q     (NEVER bare python; PATH is 3.14)
    cd frontend && npx tsc --noEmit

Expected: CI's count, ruff clean, tsc clean, `next build` green. Check
`/api/health` `git_sha` against `origin/main` before assuming anything is
live. The terminal spread/total look was **VETOED by Joe 2026-08-21 16:11Z**
(`docs/measurements/2026-08-21-spread-total-edge-second-look-result.md`) —
nothing fires at 22:40Z. **The H4 look series is CLOSED — BLOCKED ON
INSTRUMENT, 2026-08-21** — do not build the A9–A12 analyzer and do not re-run
the channel diagnostic (A17.6/A17.11).

## 2026-09-11 (eleventh session) — the spine named a column that does not exist, the widening was seen firing, and the index that would fix `/api/window` is built and deliberately not shipped

**The session's finding is that three separate things everyone had written
down were wrong in the same direction: they described a mechanism that was
never there.** CLAUDE.md's money-path paragraph named a database column that
does not exist. CLAUDE.md called a measurement "still unrun" that is
deliberately refused. And `widened_from`, recorded for days as never observed,
fires fine — it had been spot-checked at the wrong phase of the sweep cycle.
None of the three was a code defect. All three were the record drifting from
the thing it described, which is the failure mode this file exists to catch.

**STATE at close.** `main` = **`52d1dd0`**, pushed, CI green (runs 34569311226,
34569985161, 34570679419). Four commits: `e00af51` the spine corrections and
the pyarrow bump, `5e3ea5f` the guard that went red on it, `76f5e3c` the lane A
merge, `52d1dd0` the NEXT.md split. **Live = `52d1dd0`**, deployed with
`-e GIT_SHA=` and read back off `/api/health` rather than inferred; recorder
writing, live quotes up, arming unchanged (hand path armed, engine and bids
dry). ADR **0142** taken. Odds path untouched: **the freeze to 10:00Z
2026-09-14 holds** — `git diff --name-only` against `backend/odds/` and
`backend/scheduler.py` returns nothing for every branch this session produced.
**Credits: zero spent.** Every live call was a GET on a route with no visit
registration (`/api/parlays`, `/api/window`, `/api/exposure`, `/api/health`);
no lookup was minted and no combo tap taken, so **Arm D's frame is
uncontaminated by this session.** The 300/300 attention slice was already
spent ~6 hours before the session opened. No open Dependabot alerts.

### JOE'S ANSWERS, 2026-09-11 — all three yes

Put to him as three lettered questions with a recommendation on each; he
answered "yes to all" and asked that they be saved here.

- **(A) Start a fresh session after lane D lands.** Procedural. Acted on.
- **(B) The exposure gloss at the buy button STANDS.** It replaced a false
  reassurance -- the old text promised a cap that ADR 0112 removed on his own
  instruction, and it renders **at the buy button**, which is the worst place
  in the product to carry a comforting untruth. **Now pinned in words**
  (`TestTheExposureGlossIsJoesRatifiedCopy` in
  `tests/test_manual_ticket_exposure.py`), with the same force as the #9 tab
  ledes: the ratified sentence verbatim, a worked-example guard, and a guard
  that the killed claim ("exposure cap bounds", "cannot take the whole
  bankroll") **cannot return in any spelling**. Verified by disabling --
  restoring the old sentence turns two tests red. A future session will read
  "nothing caps it" as alarming copy and want to soften it; it is not
  alarming, it is the fact, and the softer version is the one that was wrong.
- **(C) #36 props as parlay legs: SPEND THE ~14 CREDITS.** Recorded on the
  ticket (comment 5634130986). **This authorises one prop sweep on one event,
  once, after 10:00Z 2026-09-14 — and nothing else.** It does **not**
  authorise leaving props in `ODDS_MARKETS`: buying a market type costs
  credits on *every* sweep thereafter (ADR 0140), so making it permanent is a
  separate decision with a recurring bill. Then either append
  `STAGED_PROP_CARD` to `CARD_SHAPES` (one line, already built and tested) or
  close the lane **on a number**.

### READ THIS FIRST: lane B is finished, on a branch, and must NOT be merged or deployed before 10:00Z 2026-09-14

Branch **`lane-b-window-index`** (`8b02d81`, `65ab0ec`), complete, tested,
CI-clean on its own tree, **deliberately not merged**. It adds
`idx_odds_window` — a covering index for `/api/window`'s `fixture_freshness`
query, which schema v39 does not touch and which is the dominant *continuous*
read on the box (four SSR pages on load, `RefreshWhenPriced` at 3s then 10s,
`Nav.tsx` on every visible tab, plus `run_loop.py`).

**It is on a branch rather than on main for one reason: a deploy ships it.**
The boot index build is budgeted at **2-4 minutes** on live, and `main` is
kept in sync with live by habit — so a merge would very likely be deployed by
the next session, and Arm D runs **Sunday 2026-09-13**. A multi-minute boot
during a registered measurement is the kind of avoidable collision that is
obvious only afterwards. `scripts/lane_board.py` reads every local branch, so
the work is discoverable by the documented mechanism rather than by memory.

**Merge checklist, for the session that takes it after the freeze lifts:**

1. `git fetch`, then **re-take schema v40** — it is a placeholder taken without
   reading `schema.sql` or `LANES.md`. `SCHEMA_VERSION`, the `_MIGRATIONS` key,
   the `schema v40` line in `schema.sql` and `VERSION` in the test all move
   together.
2. Number `docs/adr/DRAFT-a-single-arm-timing-is-not-evidence.md`. It amends
   ADR 0141 — 0141 says *time it*, this says *how*.
3. Re-run the suite on the merged tree; the branch is based on `fcca0ac` and
   main has moved.
4. Deploy, and **do not trim the 600 s health grace** — it is what covers the
   boot build.

The numbers, and read the caveat with them: at live's shape (3.63M rows,
2,640 events) the statement goes **3,904-4,399 ms -> 667-797 ms**, a paired
ratio of **5.1x-6.1x across every cache regime the rehearsal box produces**.
**That is a FLOOR, not a magnitude** — the rehearsal is at worst partly cached
on a fast SSD and live is I/O-bound against 5.19 GB, which is exactly the
regime where what the index removes (~1.46M table-row fetches per call)
dominates. v39's local 3x came back as 81x on live. Cost: **71.2 bytes/row,
~263 MB** on live's 3,696,485 rows, against v39's 190 MB; a 900-row sweep goes
9.5->12.5 ms resident and 24.9->40.7 ms under cache pressure, which is
milliseconds every ten minutes to buy a read that happens every 3-10 seconds.

**The method finding is worth more than the index, and it changed a
conclusion.** The identical query over identical data read **1,283 ms in one
session and 3,904 ms in the next**, purely on page-cache residency — a 3x
swing that would have supported any "ratio" between 1.6x and 15x had the two
arms been timed in separate runs. Every arm is now timed **round-robin in one
process**. Under that method a drafted finding did not survive: a claimed
222-vs-184 ms win for the five-column index over a cheaper four-column form is
really **2-9%**, and the record now says so and names dropping
`book_updated_ms` (25 MB back, cheaper writes) as the first thing to give up
if live shows memory pressure. That is the DRAFT ADR.

### Item 5 is CLOSED — `widened_from` fires, and the reason nobody had seen it

Over four minutes on live, same commit, same slate:

    04:00Z   tonight 0/7, tomorrow 0/7, 48h 0/7   bare call: widened_from None
    04:04Z   tonight 0/7                          bare call: widened_from 'tonight',
                                                  window -> tomorrow, 4 of 7 cards

The mechanism works end to end and `widened_words` renders the settlement
caveat. The 04:00Z reading is **also correct** — every window was empty, so
the ladder fell through and returned `tonight` unwidened, which is the
documented branch.

**What actually moved is freshness.** `kickoff_outside_window` held at ~434
across both reads while `stale_consensus` fell **256 -> 36 -> 31**: a sweep
landed. So the desk's card yield is a **sawtooth whose period is the sweep
cadence**, and a mechanism that only has somewhere to widen into in the
minutes after a sweep reads as dead to anyone who spot-checks it. This is the
**third** distinct reason this screen has been empty — the menu (refuted,
ninth session), the clock (ninth session), and now freshness — and the first
that is time-varying. Written to `lessons.md` as the pattern. **Deliberately
NOT written as a measurement doc**: three reads is G = 1, it establishes a
mechanism and cannot support a rate, and a `docs/measurements/` file would
invite someone to quote one.

**The Freshness copy gap the partner suspected does not exist.** `/api/window`
reported `fixtures_upcoming: 428`, `fixtures_fresh: 0`, so `nothingFresh` is
true and the block speaks even with `stale_consensus` at 0. Joe's screen at
04:00Z would have told him why it was empty. The ninth session's fix works;
that loop is closed.

### The three corrections to the record

1. **CLAUDE.md's money-path paragraph was wrong three ways.** `manual_orders`
   has **no `fill_price_tenths` column** — it is `limit_price_tenths`, written
   at **intent** time (`store/manual_orders.py:648`) from
   `OrderRequest.fill_price_tenths` (`kalshi/orders.py:298`). `OrderOutcome`
   has no such property, so nothing the venue returned was ever in it. The
   cited `routes.py:3957` is `:3959` and points at a different table anyway
   (`parlay_positions.stake_tenths`, via `contracts * fill_price_tenths` at
   `:4318`). **Each verified against source, not taken on report.** The claim
   that matters is untouched: the recorded basis is the ask the desk sent,
   both errors run cautious, the hedge figure is an upper bound. **The
   pre-registration's §0.1/§2 repeat the same three errors and are NOT yet
   fixed** — see open item 3.
2. **The `anchored_on_sharp` split is deliberately refused, not unrun.**
   `scripts/inspect_live_db_decisions.py:234` declines to compute it by
   design: a query carrying a decision rule is not a dump. "Still unrun"
   implied an owner who does not exist. Rewritten rather than deleted, so the
   question survives without the phantom task.
3. **`test_has_callers.py` is 122 tests in 198.7s**, not the 300s reported to
   me. Measured before writing it down.

### What else shipped

- **The exposure line, inside `ManualTicket` — ADR 0142, rank 1.** ADR 0112
  removed all five brakes and those caps were the only consumer of Joe's
  exposure figure in the product; nothing has read it since, and `/parlays` —
  where all four real combination bets were placed — fetches no position data
  at all. `GET /api/exposure` is a new minimal route rather than a reuse of
  `/api/bets`, which drags `bets_record(limit=200)`, `pass_summary` and
  `lockout_until` along for a buy button. All **seven** mount points get it
  from one edit. Verified on live: 200 in 0.27s, 401 without the cookie.
  **It informs and never blocks** — `canConfirm` does not read the exposure
  state, re-verified here by mutation rather than inherited (adding
  `exposure?.refused !== true` to `canConfirm` turns
  `test_the_confirm_predicate_does_not_read_the_exposure_state` red). A gate
  there would be a sixth ceiling and a reversal of ADR 0112. Unreadable
  renders the server's refusal words, never `$0.00`.
- **JOE-GATED, and it is the one thing here that wants his eye: the glossary's
  `exposure` definition changed.** It said *"The exposure cap bounds that
  total, so one bad night cannot take the whole bankroll."* That has been
  **false on the hand-bet path since ADR 0112**, and this definition renders
  **at the buy button** — a false reassurance, in the flattering direction, at
  the worst possible place. It now says nothing caps it on a hand bet, with a
  worked example. Kept because it is a correctness fix; the wording is his to
  overrule.
- **pyarrow 19.0.1 -> `~=25.0`, and the pip-audit ignore list is now EMPTY.**
  25 and not 23 because GHSA-rgxp-2hwp-jwgg is fixed in 23.0.1 and `~=23.0`
  would still admit the vulnerable 23.0.0. Verified the way CI verifies it:
  `pip-audit --strict` with zero ignores reports clean, and `seed_demo` +
  `store.publish` runs green under 25.0.1. pyarrow is imported only by
  `store/publish.py`, a CI-only CLI, so nothing on the serving path touches
  it and the bump cannot affect a boot.
- **NEXT.md split at 76.6% -> 37.2%**, the lowest any split has been taken at.
  Seven entries to `archive/next-2026-09-11.md`, date boundary at 2026-09-09,
  md5-verified, index lines in the same edit.
- **Two lessons**: the sweep-phase confound, and the reachability ratchet's
  blind spot.

### The guard that went red, and why that is the system working

Emptying the pip-audit ignore list turned
`test_marts.py::TestThePipAuditIgnoreListIsPinned` red on CI. **The guard is
right and was not weakened** — its own message says a removal "should mean the
bump landed, which is the good case, and still deliberate", so
`EXPECTED_IGNORES` is now the empty set with the trail in the comment.
Verified by disabling: adding a fake `--ignore-vuln` to `ci.yml` turns it red
again, so an empty expectation is still an assertion and not a vacuous pass.

**I missed it pre-push** by narrowing the test search to files that also
mention `CLAUDE.md`; `test_marts.py` does not. The grep that would have found
it is the unnarrowed one. Pattern: **narrowing a "what tests pin this?" search
by an unrelated predicate is how a pinned fact gets missed.**

### Two lane-hygiene facts worth keeping

- **Lanes share the scratchpad directory.** Lane B had a scratch file
  (`mutate.py`) overwritten mid-run by another lane. Worktrees were
  unaffected, but scratch files need unique names.
- **Do file moves in BINARY.** A text-mode round trip on Windows rewrites
  every line ending, so a seven-entry move renders as a whole-file diff and
  the only property a reviewer can check — that nothing outside the moved
  range changed — disappears. The split's diff is 20 insertions and 1,729
  deletions, which is the shape that can be inspected. In the split log.

### Still open, in order

1. **DO NOT TOUCH THE ODDS PATH BEFORE 10:00Z ON 2026-09-14.** Unchanged.
2. **SUNDAY 2026-09-13 — Arm D, a scheduled run, not a task to plan.**
   Unchanged. Take NO combo taps before then; every lookup mints into its
   sampling frame.
3. **The recorded-fill-vs-venue-charge census.** Partner's call, adopted:
   **do the unconditional parts now, defer the census itself to a trigger.**
   Branch 8.1 was the CLAUDE.md correction — **done this session**. Branch 8.2
   is item 4 below. What remains is a four-row census, deferred to **the first
   session after the 10th real fill, or 2026-11-01, whichever comes first**:
   the `fills` window from 2026-09-08 does not close until ~December, so
   perishability buys two months and n≈12 is worth reading where n=4 is worth
   arguing about. **Still binding when it runs**: not via
   `manual-orders-audit` (`fills` is in `FORBIDDEN_TABLES`); a separate named
   harness; a census, not an estimate — no mean, no rate, at any n.
   **The registration's §0.1/§2 still repeat the three
   `fill_price_tenths`/`OrderOutcome`/`:3957` errors corrected in CLAUDE.md
   this session.** Fix them before the census runs, not after.
4. **Persist the venue's own fill numbers — rank 4, NOT started.** It collides
   with lane B on `schema.sql` and `db.py`, and lane B is unmerged, so it was
   held rather than run. `record_outcome` (`store/manual_orders.py:765`)
   writes only `status`, `kalshi_order_id` and `error_text`, dropping
   `fill_count`, `average_fill_price_dollars` and `average_fee_paid_dollars`
   on the floor. Those survive only in `fills`, on a ~3-month window;
   `manual_orders` is permanent. Three nullable columns plus a schema bump
   makes every future hand bet self-describing and is the only path to a hedge
   figure that could eventually be exact. **Needs its own ADR — the census
   registration's §8.4 explicitly does not authorize money-touching changes,
   so do not cite it as cover.** Sequence it after lane B.
5. **`#36` props as parlay legs — ANSWERED, and blocked on the freeze.**
   **Joe said spend the ~14 credits (2026-09-11).** One prop sweep, one
   event, once, after 10:00Z 2026-09-14 — not a standing `ODDS_MARKETS`
   change, which would bill every sweep forever. `STAGED_PROP_CARD` is built,
   tested and deliberately not in `CARD_SHAPES`; enabling is one line and is
   correct only after a sweep has bought prop rows. `ODDS_MARKETS` on live is
   `'h2h,spreads'`. ~14 credits on one event after 10:00Z 2026-09-14, then
   register the card or close the lane on a number.
6. **The pair test** — blocked to 2026-09-13, needs a `parlay_lookups`
   pre-existence column. **Its old justification is dead**: it said it was only
   worth a migration if item 3 produced one, and v39 shipped for the index
   instead. Make it fund its own schema change or drop it.
7. **The combo fee-model reopen trigger** (n = 68) — standing no. Its home is
   a comment at the site that would fire it, not this list.
8. **The binned card** — **struck.** A closed decision, not open work: Joe
   binned it 2026-09-09 and the reason is permanent (`bet_estimates` holds one
   row and it is `is_study_row = 1`). Its home is CLAUDE.md's "Do not rebuild
   these" table, and it should be moved there rather than carried here again.

**Struck from the list this session, all on the partner's reading and none of
them work:** the ninth session's 0c, 0d and 0e (notes, not tasks — 0d says
"measured, closed" in its own text and 0e says "do not open without a
symptom"; 0e's home is the docstring of `inspect_live_db.py
parlay-candidates-timing`), the `pip-audit` pyarrow ignore (done), item 5
(done, above), and the `anchored_on_sharp` phantom (deliberately refused, not
owned).

**Closed this session:** item 5, the pyarrow ignore, rank 1 (exposure line),
rank 3 (spine corrections), rank 6 (NEXT.md split), rank 7 (two lessons and
the strike). **No ADRs are owed** — 0142 is taken and lane B's draft is
numbered at its merge.

---

## 2026-09-10 (tenth session) — one scan per request, a quote that says when it was read, and a warning that went silent as the outage got worse

**The session's finding is that "add props as parlay legs" has two gates and
only one of them costs money.** Everyone had it costed as a feed decision:
a prop cannot be a leg unless a sportsbook price was bought for it, and buying
a market type costs credits on every sweep forever. True, and not the binding
constraint. **Every parlay recipe declares which markets it draws from and all
seven decline props** — `TEAM_MARKETS_ONLY` (`backend/core/ladder.py:138`), six
recipes, plus one spreads-only — a free gate nobody had written down. And the
paid gate is **NOT open** -- a claim to the contrary was published and
withdrawn the same session, and the withdrawal is the more useful finding.

**THE CORRECTION, MEASURED ON LIVE. Read this before planning any prop work.**
`CANDIDATE_SQL` admits five MLB prop markets (`backend/parlays.py:611-613`)
and the prop arm resolves them to legs with a real Kalshi rung -- the code
path is open end to end. **There are no rows.**

    ODDS_MARKETS on live                  'h2h,spreads'
    newest MLB prop row in fair_prices    600.5 hours old (~25 days)
    prop rows in the last 24h / 7d        0 / 0
    h2h / spreads rows in the last 24h    65,032 / 71,044
    usable legs in tonight's pool         7, of which props: 0

So **"the query admits this market" and "the desk holds this market" are
different claims**, and the first was reported as the second. Both gates are
shut, the expensive one binds after all, and there is no free test: buying
prop rows changes `ODDS_MARKETS` / the prop sweep, which costs credits on
every sweep thereafter and edits `backend/odds/`, **frozen to 10:00Z
2026-09-14**. The 25-day-old rows cannot stand in -- they are outside the
freshness rule and outside the candidate scan's own two-hour floor.

Joe answered **B1** ("run the free baseball prop test") against the wrong
premise. He has been told. The corrected choice is the one the ticket body
already had: **~14 credits on one event after the freeze lifts, or close the
lane.**

**STATE at close.** `main` = **`7f0f85f`**, pushed, CI green (run
34520670775 on `5042d15`, and the one docs commit after it). Four commits:
`a5b7460` the pre-registration, `1fdba22` the three lanes, `5042d15` the
session files, `7f0f85f` a lesson. **Live = `7f0f85f`**, deployed with
`-e GIT_SHA=` and read back off `/api/health` rather than inferred; recorder
writing, live quotes up, arming unchanged (hand path armed, engine and bids
dry). Full suite on the tree as committed: **6,938 passed, 10 xfailed, 0
failed** (10m29s); ruff and tsc clean. Odds path untouched: **the freeze to 10:00Z 2026-09-14 holds** — nothing
under `backend/odds/` or `backend/scheduler.py` was read for edit or written.
**Credits: zero spent.** No lookup was minted, no combo tap taken, nothing
authenticated was called against Kalshi except one read-only `flyctl ssh` for a
library version — **Arm D's frame is uncontaminated by this session.**
ADR 0140 taken. Dependabot: no open alerts, and the `cryptography` blind spot
is closed (below).

### THE 503 HAS A CAUSE, AND IT IS A MISSING INDEX — schema v39

Chasing why the desk was still answering 503 `read_budget_exceeded` an hour
after the cache-eviction incident below, `inspect_live_db.py
parlay-candidates-timing` gave the numbers:

    whole candidate scan                        73,526 ms   (494 rows)
    odds_snapshots MIN(commence_ms) GROUP BY    26,719 ms   (703 rows)
    fair_prices rows inside the scan window            848  of 10,112,298
    odds_snapshots rows                          3,696,485
    live database                                   5.19 GB

**848 rows in the window and 73 seconds to return them**, so the row count was
never the problem. The plan named it: `SEARCH o USING AUTOMATIC PARTIAL
COVERING INDEX` — SQLite building a temporary index at query time because no
suitable one exists.

**`CANDIDATE_SQL`'s own comment claims an index that has never existed.** It
says the plan is a seek "with it, plus `idx_odds_event_commence`". Live has
`idx_odds_commence`, `idx_odds_event` and `idx_odds_sport_commence`, and no
`idx_odds_event_commence`. The 2026-08-26 fix was half-shipped: the subquery
restriction landed and the index did not.

**It did not land because it was deliberately removed, and the reasoning was
wrong in an instructive way.** `schema.sql` recorded it: with the index and
without it, the step reads `SEARCH ... (odds_event_id=?)` — "identical shape",
so it "changed no plan" and would cost write amplification for nothing. Both
observations are true. **`EXPLAIN QUERY PLAN` reports the access method, never
how many rows the method touches.** The subquery takes `MIN(commence_ms)` per
event; `idx_odds_event` is `(odds_event_id, market, fetched_ms DESC)`, so the
minimum can only be found by reading every row of the group — ~1,400 per event
— and fetching the column from the table. With `commence_ms` second, the
minimum is the first entry.

Reproduced locally at live's shape (800 events x 1,400 rows), warm, best of
three: **503.9 ms without, 167.5 ms with**, the two plans differing only in the
index name. That 3x is a **floor** on the live win, not an estimate of it: the
local box is CPU-bound with the table in memory and live is I/O-bound against a
5.19 GB file, which is the regime where rows-touched dominates.

Shipped as **schema v39** (`idx_odds_event_commence`), with the measurement
stored beside the CREATE in `schema.sql` and pinned by
`tests/test_odds_event_commence_index.py` — **the index and the recorded reason
are guarded separately**, because an index whose justification was deleted is
one somebody removes again on the same argument as last time.

Two existing tests went red and both were name-pinning rather than claim-pinning:

- `test_no_duplicate_leading_column_index_was_reintroduced` asserted the index
  did NOT exist. **Inverted, not deleted** — the original rule (do not pay
  write amplification for nothing) is intact; what changed is what counts as
  evidence of "nothing", and a plan diff cannot supply it.
- `test_odds_snapshots_is_searched_not_scanned` failed on an **improvement**:
  the refused-leg kickoff lookup went from `SEARCH o USING INDEX
  idx_odds_event` to `SEARCH o USING COVERING INDEX idx_odds_event_commence`,
  which stops touching the table at all. A guard that names an implementation
  calls a better plan a regression.
- And `test_the_odds_seek_comes_from_the_restriction_not_a_new_index` was
  passing for no reason at all: `"idx_odds_event" in step` is a **substring**
  of `idx_odds_event_commence`, so it could not have failed whichever index
  the planner chose. Rewritten to assert the seek, which is the durable claim.

**The write-amplification objection stands and is being paid deliberately:**
~52 bytes/row locally, about **190 MB** on live's 3,696,485 rows. Bought
because the desk was 503-ing in front of Joe, and because a covering seek
should *reduce* cache pressure here — it stops pulling ~1,400 table pages per
event into the page cache that is the binding resource on this box.

**VERIFIED ON LIVE, same session.** Deployed `2e66f36`, migration ran at boot,
index confirmed present and chosen by the planner. Re-ran
`parlay-candidates-timing` on the freshly-booted (i.e. COLD) container:

                                          before      after     factor
    odds_snapshots MIN GROUP BY        26,719 ms   327.9 ms       81x
    whole candidate scan               73,526 ms  11,712 ms      6.3x

and the route itself, which is what Joe touches:

    first call after deploy   503 read_budget_exceeded (25 s)  ->   3.95 s
    warm                      1.5-3.3 s historic best          ->   0.49-0.82 s

**So the cold-start 503 is gone, and the warm desk is roughly 3x faster than
its best previously recorded state.** The local 3x was a floor, as predicted;
the live subquery win is 81x because live is I/O-bound and the index removes
~1,400 table-page reads per event rather than CPU work.

**What this does NOT establish:** nothing about `/api/board`, `/api/slate` or
the recorder, which were never timed against this. And the 6-of-7 cards seen
after the deploy versus 4-of-7 before is the evening slate filling out, NOT an
effect of the index -- the index changes speed and cannot change which legs
are eligible.

### Two corrections to the front door, both verified rather than reasoned

1. **The ADR 0117 box's `cryptography` warning is stale and has been removed
   from the live reading.** It said `requirements.txt:9` still pins a version
   inside alert #15's vulnerable range. The pin is `~=50.0`, the range is
   `>= 42.0.0, <= 48.0.0`, and the running container reports **50.0.1** (read
   over `flyctl ssh`; the `Error: The handle is invalid.` after a good read is
   the known artifact). The 44 -> 50 bump (ADR 0124, 2026-09-09) closed it. The
   query is still blind to `cryptography`, so keep verifying from the
   container — but there is nothing outstanding to verify *against* today.
2. **The decision queue is empty.** All 32 sub-issues of map #3 were closed;
   only the map itself was open. So the map produces no frontier this session,
   and the only decisions outstanding are the ones put to Joe below.

### Ticket #12 is superseded, not reopened — and the convention is now written down

Joe's 2026-09-10 *"i want to bet on props for parlay legs"* reads as a reversal
of #12's *"option A — he does not really bet props; drop them from the brief"*
(2026-09-02) and **is not one**: #12 asked about props as **picks**, the new
want is props as **legs**, and a prop he would not bet alone is still a leg he
would combine. **#36** carries the new question; #12 keeps its answer, is left
closed, and now points at #36. Neither was edited to agree with the other.

`docs/agents/issue-tracker.md` gained the rule, with this as the worked
example: **never reopen a ticket Joe has answered** — reopening rewrites the
record of what he said and when, which is the thing the map exists to keep.
Check first whether the two questions are actually the same one; usually they
are not, and saying so is most of the work.

### What shipped — `1fdba22`

- **One candidate scan per request.** `build_ladder_payload_widening` called
  `ladder_candidates` once per window until one built a card, and everything
  `ladder_candidates` reads before applying the window is horizon-independent:
  `CANDIDATE_SQL` binds `(floor_ms, floor_ms, now_ms)` and never the horizon
  (the kickoff bound is applied in Python after `fetchall()`), the per-event
  `kalshi_markets` loop is keyed off the **unfiltered** scan, and
  `combo_eligible_events` takes `now_ms` only. Split into `CandidatePool` /
  `candidate_pool`, read once and filtered per window; the windows are strictly
  nested, so that is provably the same answer.
  **The duplication was bigger than item 0b claimed** — `1 + N` statements per
  window, not one query per window. Measured on a three-game bed that widens
  once: **two scans and six per-event reads before, one and three after.**
  A pool carries the `now_ms` / `max_odds_age_ms` it was built for and
  `ladder_candidates` refuses a mismatch rather than answering for the wrong
  minute. That guard was **decoration until its own test existed** — the first
  mutation run came back green.
- **The combo quote now says when it was read.** `quoted_ms` and
  `quote_max_age_ms` travel with the priced payload, the threshold **passed
  from the route** (`staleness.max_kalshi_quote_age_s`) rather than re-derived,
  so it cannot drift from what `serialise.py` marks `price_is_current` against.
  `QuoteAge` renders a ticking age and marks itself past the limit. It
  **relabels and never blocks** — ADR 0112 removed all five ceilings on a hand
  bet and a staleness gate on the buy would be a sixth.
- **`Freshness` stopped going silent as the outage got worse.** See the lesson;
  the gate now also fires on `/api/window`'s fixtures-upcoming-with-none-fresh,
  and the zero-count branch no longer says "all 0 candidate sides were refused
  on age".
- **ADR 0140** — the parlay leg pool is odds-feed-driven.

### The `test_stale_exit.py` guard, and why it was rewritten rather than loosened

It pinned the literal `stale === 0 || unbuilt === 0` while its docstring stated
the claim: a banner that fires on a working screen is one the reader learns to
skip. The replacement **preserves that claim exactly** and the test went red
anyway, because it was pinning characters. Rewritten to assert the claim, plus
the half it was missing, and it additionally refuses the old predicate's
return — **strictly stronger than what it replaced.** Lesson written.

### Guards verified by disabling

    widening no longer shares the pool          4 red
    pool reuse guard (`now_ms` mismatch)        2 red   (green on first pass)
    threshold dropped from the priced payload   1 red
    buy control given a `disabled` prop         1 red
    Freshness gate back to the row-only test    3 red

### Joe has two letters and one FYI — artifact published

<https://claude.ai/code/artifact/b2289b51-be1e-4b12-af59-b09b0db876df>

- **(A) the `/parlays` lede wording — ANSWERED A1, 2026-09-10: "hardly
  anyone" stands.** Given the replacement in place, the two shard-1 books
  behind it and two alternatives, he kept it. So #9's sentence is his approved
  copy in full again rather than a correctness patch awaiting an answer, and
  changing it is his call. Recorded on ticket #9 and in the two files that pin
  the sentence verbatim.
- **(B) props as parlay legs**, re-put with the two-gates finding: try it free
  in baseball now (recommended), wait and buy the NFL measurement, or close the
  lane. The correlation limit is stated in the artifact rather than discovered
  after.
- **(C) FYI, no answer wanted:** his "take the trade" answer is **withdrawn and
  not being acted on**, per the partner's ruling. Do not re-ask it. ADR 0110
  dates the lever to 2026-09-28 regardless, so nothing is lost.

### Still open, in order

0c. **COLD START IS FIXED, AND THE RESIDUAL IS NAMED.** The desk warms its own
   read path at boot (`scripts/warm_read_path.py`, run backgrounded and
   **disowned** by the entrypoint). Measured on live across three deploys:

       cold boot, before            20.5 s   (25 s read budget -- it barely fit)
       warm-up itself                9.9 s   (logged: "[warm] ... warmed in Ns")
       first request, after          0.81 s
       warm                          0.50 s

   **The residual: a request arriving DURING the warm window still waits.** The
   warm starts once uvicorn is healthy (~13 s in) and runs ~10 s, so roughly
   the first 25 seconds after a boot are unprotected. That is acceptable
   because a deploy is a deliberate act and Joe is not tapping inside it --
   but it is not "solved", and an unlucky Fly-initiated restart could still
   land there. Do not report it as eliminated.

   **Two things that make this checkable:** the boot log line carries the
   elapsed time AND the leg count, so a warm-up that read an empty database is
   distinguishable from one that worked; and `tests/test_warm_read_path.py`
   runs the script as a subprocess by path, which is the only way to catch the
   class of bug that shipped here (see below).

0e. **The whole candidate scan is still ~10 s on a genuinely cold box**, which
   is what the warm-up now absorbs rather than removes. If the desk ever feels
   slow again this is the number to attack; there is no symptom today, so this
   is a note rather than a task. `inspect_live_db.py parlay-candidates-timing`
   is the instrument. The subquery is no
   longer the cost (327.9 ms of it); what remains is `fair_prices` and the
   joins. It is comfortably inside the 25 s budget now and there is no
   symptom, so this is a note rather than a task -- do not open it without
   one. `inspect_live_db.py parlay-candidates-timing` is the instrument.

0d. **THE COLD-START 503 WAS NOT THE WIDENING, AND THAT IS MEASURED
   RATHER THAN SUSPECTED.** Deployed `7f0f85f` and read `/api/parlays` three
   times immediately after:

       attempt 1 (cold)   503 read_budget_exceeded   25.0s
       attempt 2          200, 4 of 7 cards          10.8s
       attempt 3 (warm)   200, 4 of 7 cards           1.5s

   **`widened_from` was `None` on both successes** — `tonight` built four
   cards, so the widening loop never ran and the 503 landed on a request that
   took **one** `ladder_candidates` scan. The ninth session's item 0b read the
   two events as coinciding by construction; they do not. A cold container
   against a 10M-row database blows a 25s budget on a single scan, which is
   the same page-cache effect as the 74.8s-cold / 2.15s-warm measurement in
   `lessons.md` — the 5GB file does not fit the ~1.4GB cache and a fresh
   machine has none of it.

   So the dedup shipped in `1fdba22` is right on its own terms and buys
   nothing here. **Do not write it up as the fix, and do not chase the
   widening further.** The real question is a cold box serving a 25s budget:
   warm the candidate path on boot, raise or stage the budget for the first
   request after start, or accept a 503 on the first tap after a deploy and
   say so on screen. Not chosen — it is a design call and it wants
   `runtime-realist` on what actually runs at boot before anyone picks.

   **Joe-visible consequence, worth knowing before he taps:** the first
   `/parlays` load after any deploy is likely to fail, and a retry ten
   seconds later works. Every deploy has always done this; it was read as a
   one-off in the ninth session and it is not.

B1. **STAGED AND WAITING ON DATA, NOT ON CODE.** Joe chose B1; the free test
   did not exist (see the correction above). What was built instead:
   `STAGED_PROP_CARD` in `backend/core/ladder.py` -- a complete, tested,
   **deliberately unregistered** prop card, staged the way `NFL_PROP_SERIES`
   was in `8d5dd1c`. `tests/test_staged_prop_card.py` proves it builds, takes
   one leg per fixture, and refuses a lottery leg.
   **Enabling it is one line -- appending it to `CARD_SHAPES` -- and that line
   is correct only AFTER a sweep has bought prop rows.** Registering it now
   puts a card on Joe's screen that reads "needs 2 fresh games and the slate
   has 0" forever, which reads as a thin slate rather than as a market the
   desk does not buy.
   Two things the machinery already had, and neither needed writing:
   `min_leg_probability` exists for exactly this card (its own comment calls
   it required on any card admitting props) and is set to 0.20, worst case
   ~125x; and `_best_per_game` is an explicit "structural same-game guard", so
   the correlation risk raised with Joe cannot occur however the recipe is
   tuned.
   **The remaining question is entirely about the feed**, is not free, and is
   blocked to 10:00Z 2026-09-14 -- ~14 credits on one event, then either
   register the card or close the lane on a number. ADR 0140 is why this was
   always a feed decision.

1. **DO NOT TOUCH THE ODDS PATH BEFORE 10:00Z ON 2026-09-14.** Unchanged.
2. **SUNDAY 2026-09-13 — a scheduled run, not a task to plan.** Unchanged, and
   still carrying the eighth session's disclosure.
3. **The recorded-fill-vs-venue-charge census.** Registered this session:
   `docs/measurements/2026-09-10-preregistration-recorded-fill-vs-venue-charge.md`.
   **Read the registration before running it — two things in it are binding.**
   It may NOT be implemented by adding a join to `manual-orders-audit`
   (`tests/test_inspect_live_db.py` lists `fills` in `FORBIDDEN_TABLES` and is
   right to be absolute); route it through a separate named harness, as
   `2026-09-09-fee-alarm-replayed-over-every-hand-fill.md` did. And it is a
   **census, not an estimate** — no mean, no rate, at any `n`; per-row output
   ordered by `submitted_ms` ascending and by nothing else.
   **Both decision branches are unconditional, so this decides nothing** — it
   captures a fact before the ~3-month `fills` window drops it, which is a
   different and smaller reason. The `/hedge` "exact" wording was already
   corrected in CLAUDE.md this session and a clean result does not restore it.
4. **Total-exposure line at the buy button** — and the partner's design call
   changes the shape: put it **inside `ManualTicket`** so all six mount points
   get it from one edit, fed by a small dedicated route. `open_positions`
   (`backend/bets.py:502`) is served only by `GET /api/slate`, and `/parlays` —
   the screen all four real combination bets were placed on — fetches none of
   it. The cheap `/slate` prop-threading covers the screen he does not buy on.
5. **Check `window.widened_from` on live on a weekday morning.** Still never
   observed firing. A GET, costs nothing, five minutes inside any lane.
   **And do not repeat the item's own reasoning**: the widening runs only when
   the caller names no horizon, so the 2026-09-10 histogram (taken with
   explicit horizons) says nothing about how often it fires.
6. **The pair test, re-specified** — unchanged, blocked to 2026-09-13, still
   needs the `parlay_lookups` pre-existence column first. Only worth a
   migration if item 3 produces a schema v39 anyway.
7. **The combo fee-model reopen trigger** (n = 68) — standing no. Unchanged.
8. **`pip-audit` pyarrow ignore**, **the binned card** — unchanged.

**Closed this session:** the ninth session's item 0b (scan dedup shipped; the
`widened_from` observation survives as item 5), item A (withdrawn, not
deferred — see (C)), item B (superseded by #36), the ninth session's item 5
(`Freshness`, was a conjecture, was true, fixed), item 6 (NFL prop fixture
capture — done in `8d5dd1c`; KXNFLANYTD had 0 open events, which is a venue
state and not a task). **The second owed ADR is not owed** — it was conditional
on the sharp-anchor re-ask surviving, and the re-ask is withdrawn.

---

## 2026-09-10 (ninth session) — the parlay screen was empty on the clock, not the menu, and NFL prop ladders need no parser

**Joe opened with "I have to make parlays more wide and variety options with
over unders, props, underdog, etc." The variety was never the bound.** Measured
on live at 16:4xZ: the `tonight` pool held **one** game and all seven cards read
"needs N fresh games and the slate has 1", while the SAME slate, the same
markets and the same minute built **six of seven** one day out. The excluded
histogram is `kickoff_outside_window: 440`, `stale_consensus: 9` — so 440 of 449
excluded legs were cut by the clock, and **adding totals or props would not have
filled one of those cards.**

**STATE at close.** `main` = **`76cc97c`**, **pushed**, CI green
(run 34510972323). Three commits: `8d5dd1c` the NFL prop capture, `d56638a`
the horizon widening, `76cc97c` this state line. Full suite on the tree as
committed: **6,908 passed, 10 xfailed, 0 failed** (20m07s); ruff and tsc
clean. **Live = `76cc97c`**, deployed 2026-09-10 ~18:0xZ with
`-e GIT_SHA=`, read back off `/api/health` rather than inferred; recorder
healthy, live quotes up, arming unchanged (hand path armed, engine and bids
dry). No open Dependabot alerts on the push rescan — noting that the query
still cannot see `cryptography`, so that is a clean *listing*, not a clean
*tree*. Odds path untouched: the freeze to 10:00Z 2026-09-14 holds. No ADR
taken, two owed (below). Credits: **zero spent** — the capture is
unauthenticated `/events`, the histogram and the post-deploy checks are GETs
of `/api/parlays`, and no lookup was minted, so Arm D's frame is
uncontaminated by this session. Odds path
untouched: the freeze to 10:00Z 2026-09-14 holds; nothing under `backend/odds/`
or `backend/scheduler.py` was read or written. No ADR taken, and two are owed
(below). Credits: **zero spent** — the capture is unauthenticated `/events`, the
histogram is a GET of `/api/parlays`, and no lookup was minted, so Arm D's frame
is uncontaminated by this session.

### Joe's two answers, and one of them should be re-asked

Batched as (A)/(B); he answered both in one line, as usual.

- **(A) "take the trade"** — accept losing the sharp anchor to admit totals.
  **Re-ask this.** He answered BEFORE the histogram existed. The trade is
  ADR 0110's: dropping `eu` is the only lever that admits totals, and
  `SHARP_BOOKS = {pinnacle, betfair_ex_eu, betfair_ex_uk, matchbook}`
  (`runner.py:153`) contains no `us`-region book, so under `us` alone the sharp
  set is **empty** and sharp anchoring was **73.0%** of the pinned record. He
  traded that away to fix an empty screen that this session then showed was
  empty for an unrelated reason. Dated 2026-09-28 regardless, so nothing is
  lost by putting it again with the histogram attached.
- **(B) "i want to bet on props for parlay legs"** — props are UNKILLED, and
  this **overturns map ticket #12** (resolved by Joe 2026-09-02: *"option A —
  he does not really bet props; drop them from the brief"*). The narrower want
  is legs, not picks. #12 needs reopening or superseding; it is currently
  closed and says the opposite.

### What shipped

- **`8d5dd1c`** — the NFL prop capture. `scripts/capture_nfl_prop_fixture.py`
  and `tests/fixtures/events_nfl_props_nested.json`, unauthenticated, no
  credits, nothing minted. **The finding is that NFL needed no new parser:**
  the MLB grammar `"Player: N+"` and the join identity `floor_strike == N - 0.5`
  hold **2,029 of 2,029** across KXNFLPASSYDS (253), KXNFLRECYDS (1,160) and
  KXNFLRSHYDS (616) — three magnitudes, so it is a property of Kalshi's prop
  ladder rather than of baseball. KXNFLFIRSTTD is 362 markets with **zero**
  `floor_strike`, bare-name subtitles and `strike_type = 'structured'`: no
  rung, joins to nothing. KXNFLANYTD had 0 open events and is recorded as
  **unmeasured, not tested**. `props.py` split into `MLB_PROP_SERIES`, staged
  `NFL_PROP_SERIES` and `PROP_SERIES_NO_STRIKE`; **`PROP_SERIES` is unchanged**,
  so live behaviour did not move.
- **The horizon widening.** An unnamed window tries `tonight` and widens only
  if it builds no card at all; a **named** window is never widened. The
  widening announces itself in `window.widened_from` / `widened_words`, and the
  words carry the settlement caveat — Joe's rule was never about the window, it
  was *"I'd want to see my parlays finish out by the time the evening games
  end"*, so widening past it has to say the card cannot settle tonight.
  `WindowPicker` renders it. If every window is empty the `tonight` payload is
  returned unwidened, so the refusal blames the right clock.

### The mutation that passed, and why the bed was wrong

The first route test **passed a mutation that removed the guard entirely.** Its
bed was an empty database: with nothing to build, every window refuses, so a
route that wrongly widened still returned `tonight` and looked correct. Rebuilt
on a slate seeded with games *only* tomorrow — the only bed that can tell the
two paths apart. Pattern written to `lessons.md`: **a guard test needs a bed
where the unguarded code would produce a DIFFERENT answer, and "both paths
refuse" is not that bed.**

    widen silently                          3 tests red
    widen despite an explicit window        1 red
    never widen                             1 red
    return the widest window when all empty 1 red
    merge NFL into PROP_SERIES              2 red
    loosen SUBTITLE to admit bare names     1 red
    invert the join identity to N + 0.5     3 red

### Two ADRs owed

1. **The parlay leg pool is odds-feed-driven.** The join runs `fair_prices` ->
   find a Kalshi market, never the reverse (`backend/parlays.py:686-737`). That
   one sentence is why every "add a market type" request is a **feed** decision
   wearing a UI request's clothes, and it will be re-derived at full cost
   otherwise.
2. **The sharp-anchor trade**, if (A) survives re-asking. It changes what
   "fair" means on every card in every sport and cannot be a config edit.

---

## 2026-09-10 (eighth session) — a combination CAN be sold back, five screens said it could not, and three of my own claims were withdrawn

**Joe opened with "I WANT TO ACTUALLY BUY ONE COMBINATION FOR A FUTURE GAME
THROUGH THE DESK." The answer is no, and it is the venue rather than us.**
ADR 0138's horizon fix was real; fixing it revealed that nobody quotes those
books. What the session actually found is unrelated to the question and worth
more: **two `KXMVECROSSCATEGORY-SHARD1` books carried resting YES bids**, so
the universal five screens asserted — "you can enter and you cannot exit" — is
false.

**STATE at close.** `main` = **`7301129`**, pushed. `a2e690d` CI green
(run 34487598739). **Live = `158a90c`** — behind main by both commits.
Odds path untouched: the freeze to 10:00Z 2026-09-14 holds; nothing under
`backend/odds/` or `backend/scheduler.py` was read or written. No ADR taken.
One measurement document, and it is a disclosure rather than a finding.
Credits: **52 of 700** on budget day 20260910; four attention registrations
bought only two sweeps (24 credits) because the ten-minute cadence refused the
rest; attention slice 24 of 300.

### THE HEADLINE: a resting YES bid exists

```
KXMVECROSSCATEGORY-SHARD1-S202662C6B3CFEC6-5D18E47B21C
   yes_dollars [['0.0980','10.00']]   no_dollars [['0.8610','10.00']]   created 13:43:30.222636Z
KXMVECROSSCATEGORY-SHARD1-S2026D379AC93CBF-7772CD6AC5F
   yes_dollars [['0.0570','10.00']]   no_dollars [['0.9020','10.00']]   created 13:45:34.187576Z
```

One level a side, `depth=5` requested so the shape is complete. Both **minted
one to three minutes before being seen quoted** — a fresh combo book can be
two-sided. Found by a **public unauthenticated** `/markets` + `/orderbook`
read via `urllib`, no credential, no `lookup_combo`: it created nothing and
added nothing to any sampling frame. Neither is desk-minted — one leg is
`KXEPLGAME`, a league this desk cannot build, and neither ticker appears in
`parlay_lookups`.

**An existence proof kills a universal and supplies no rate.** Five surfaces
were corrected in `7301129` (buy ticket `combo_note`, the 422 acknowledgement
refusal, the bid route's 422, `NOTES["unquoted"]`, and the `ManualTicket`
fallback / `PriceOnKalshi` note / `/parlays` lede). Each now reports the two
books, **names the size** — ten contracts at a single price, because "an exit
exists" without "it is this small" trades one overstatement for its mirror —
and claims **no frequency**, which Arm D measures 2026-09-13. New sourced
constants `COMBO_EXIT_SHARD_YES_BID_{DATE,BOOKS,SIZE_CONTRACTS}`;
`COMBO_EXIT_CENSUS_SHARD_BOOKS_READ` **stays zero** on purpose (it counts
shard books inside the census of forty, and these two were not in it).

**It shipped before Sunday rather than after, and the error ran in the
CAUTIOUS direction** — Joe was told a combination is less exitable than it may
be. That is the flattering direction, which is exactly why it would have sat
for months. The `/parlays` lede is Joe's ratified copy (#9, 2026-08-27) and
one word moved: "nobody" → "hardly anyone". **Joe-gated: the final phrasing.**

### THREE CLAIMS I MADE AND WITHDREW — read this before re-deriving any of them

1. **"Moneyline combos get quoted, spread combos never do."** `measurement-skeptic`:
   **UNSUPPORTED**. My `p = 0.00095` did not reproduce (it is 0.000275; I summed
   the hypergeometric over the wrong margin). The unit is the **mint, not the
   tap** — no minted ticker in the record has EVER changed status between
   reads, including one across 6h44m — so the denominator is 13/26 vs 0/11
   (p = 0.0029), not 15/31 vs 0/17. **The parts do not agree**: 64% of the
   spread arm sits at leg counts with no moneyline comparator; at 3 legs it is
   9/17 vs 0/4 (p = 0.083), within `safe` 9/14 vs 0/2 (p = 0.175).
2. **"The horizon separates — tonight is quoted, beyond tonight never."** The
   `tonight` control arm **re-read a ticker already known to be priced**, so it
   was fixed by construction. Also confounded structurally: every
   beyond-tonight leg the desk can offer is NCAAF, because the feed buys near
   kickoff and tomorrow's MLB is not in the pool. No tap fixes that.
3. **"69% of visits open onto stale odds, so the screen is broken at the
   moment of decision."** That is the **first-stamp** reading;
   `visit-freshness`'s own docstring distinguishes it from `last_age_ms`,
   "what the visit bought itself by staying". `RefreshWhenPriced.tsx` already
   buys attention on open and re-renders when `fixtures_fresh` rises, in ten
   to fifteen seconds, and `ParlayCards`'s `Freshness` block already says why
   the desk is empty. **The item was cut, not built.**

**The confound that survives all of it, and it is unresolvable in this table:**
`lookup` **creates** the market when the combination does not exist
(`backend/kalshi/combos.py`). "Spread combos are not quoted" and "**self-minted
tickers** are not quoted" predict identical data, and the spread-bearing
recipes (`lottery` 6 legs, `longshot` = the three *least* likely games,
`short_spreads`) are exactly the combinations no human would have built.
`parlay_lookups` has **no pre-existence column**. `pre-registrar` scored the
two YES-bid books against this at LR ≈ 1.004 — no evidence either way, since
the desk's two touched tickers sit in a scanned page of ≥1,000.

### What shipped

- **`a2e690d`** — `book_empty` now passes `leg_details_for(selected)`
  (`backend/parlays.py`); 30 of the first 46 live rows carry bare tickers while
  the return payload twenty lines below built `commence_ms` off the same
  `selected`. Verified by disabling: mutation red on `KeyError: 'side'`, priced
  twin green. Item 0's stopping rule replaced (below). Two lessons.
- **`7301129`** — the five copy surfaces, the guards moved with the fact, and
  `docs/measurements/2026-09-10-disclosed-unregistered-look-combo-exit-shard1.md`.

**Guards moved, never weakened.** Three tests pinned the killed sentence *in
words* so it could not be softened out; they now pin the replacement with the
same force and additionally assert the universal cannot return
(`"cannot exit" not in detail`). `test_the_exit_census_copy_names_its_scope`
required the copy to say "nothing is known" about the shard — itself now a
demand for a false statement — and now requires it to disclaim the **rate**.
Verified by disabling: reinstating "and you cannot exit" turns
`test_kxmve_is_refused_without_the_acknowledgement` red.

### THE DISCLOSURE — read it before writing Sunday's result

`docs/measurements/2026-09-10-disclosed-unregistered-look-combo-exit-shard1.md`.
Two looks at Arm D's registered population, three days early. **α, population,
stopping rule and decision rule are UNCHANGED**, and the one inferential test
(Arm A S2 Fisher, α = 0.01) has a population neither look touched. What is
damaged: the answer is known in advance, and **my twelve taps minted into the
newest-first frame Arm D samples** — `lookup_combo(allow_market_creation=True)`
is an outward-facing write, which "it spends no money" did not reveal. Three of
those rows returned tickers earlier taps had returned, so at most twelve and
known to be loose. Dual reporting with/without desk-created rows is required.
`EXIT_PRACTICAL` scores as met at exactly its boundary and **fires nothing** —
an unregistered look does not trigger a registered rule, so ADR 0078 stays shut.

### Still open, in order

0b. **THE WIDENING'S WORST CASE IS 3x `CANDIDATE_SQL` UNDER A 25s READ
   BUDGET, AND IT WAS OBSERVED FAILING ONCE.** `build_ladder_payload_widening`
   runs one `ladder_candidates` per window until one builds, so a night where
   `tonight` is empty costs three scans in a single request. The first call
   after the 2026-09-10 deploy returned **503 `read_budget_exceeded`**
   (`budget_ms` 25000); retries were 200 in 1.5-3.3s, so it was a cold
   container rather than a standing break. **The two conditions coincide by
   construction**: the cold box is most likely right after a deploy, and an
   empty `tonight` is what triggers the extra scans. The local suite cannot
   see this -- it never runs cold against a 10M-row database.
   Bound it: cache the candidate pool across horizons (one scan, filtered
   three ways, since the windows are nested), or widen at most once. Prefer
   the cache -- `ladder_candidates` already takes `horizon` only to set an
   upper kickoff bound.
   **Also still unobserved: the widened branch has never fired on live.** At
   16:4xZ `tonight` held 1 game and built 0 cards; by 18:1xZ it held enough
   to build 4 of 7, so the fallback correctly did nothing and has been proven
   only by test. Check `window.widened_from` on a real weekday morning before
   believing the screen behaves as designed.

A. **RE-ASK JOE (A): the sharp-anchor trade, with the histogram attached.**
   He said "take the trade" — drop `eu`, lose Pinnacle and Betfair, admit
   totals — BEFORE the 2026-09-10 histogram showed the cards were empty on
   kickoff time rather than on market type. `SHARP_BOOKS` has no `us`-region
   member (`runner.py:153`), so under `us` alone the sharp set is EMPTY and
   sharp anchoring was 73.0% of the pinned record. Dated 2026-09-28 by
   ADR 0110 regardless. **Do not act on the answer he already gave.**

B. **Joe wants props as PARLAY LEGS (2026-09-10), which overturns map ticket
   #12.** #12 is CLOSED carrying his 2026-09-02 answer *"option A — he does
   not really bet props; drop them from the brief"*. Reopen or supersede it;
   a closed ticket asserting the opposite is the front door lying. The
   narrower want is legs, never picks.

C. **The NFL prop lane is buildable but its coverage is unmeasured, and the
   prior is bad.** `NFL_PROP_SERIES` is staged and tested (`8d5dd1c`);
   enabling is ONE edit with two halves — `PROP_SERIES = {**MLB, **NFL}` AND
   a sport-aware `prop_market_keys()` (`backend/odds/client.py`, FROZEN to
   10:00Z 2026-09-14; it is a flat list whose length IS the price, so three
   NFL keys there would be requested on every MLB event too). Half alone is
   broken both ways. **Measure first:** ADR 0079 put primary-only coverage at
   48 of 263 MLB prop markets (18%), NFL ladders are longer, and 35,448 of
   35,448 alternate rungs carry no Under and cannot be devigged. One event,
   ~14 credits, after the 14th. If coverage is as bad as MLB's, kill the lane.

0. **THE PAIR TEST, RE-SPECIFIED — and do not start it before Sunday.** The old
   rule said "take it again **when a moneyline card is quoted**", which
   conditions the retake on one arm's outcome; followed, it produced a
   moneyline arm 2-of-2 quoted **by construction**. Honest accounting: two
   pairs, one null (07:09Z, both arms empty), one conditioned (13:51Z). New
   rule: fixed order, **18:00Z daily for five days**, record every pair
   including double-empties. **Add the pre-existence column first** or the
   pairs cannot separate the two stories. Every lookup mints into Arm D's
   frame, so not before 2026-09-13.
1. **DO NOT TOUCH THE ODDS PATH BEFORE 10:00Z ON 2026-09-14.** Unchanged.
2. **SUNDAY 2026-09-13 — a scheduled run, not a task to plan.** Unchanged, and
   now carrying the disclosure above.
3. **Total-exposure line at the buy button** (partner's rank, sharp-bettor's
   finding #3). On the 66-of-69-invisible-positions argument ONLY — the depth
   argument died when row 49's 2,928 contracts became 152 in forty minutes.
   `backend/bets.py::open_positions` already computes a venue-sourced number
   that refuses honestly; the job is to move it above the buy control.
4. **The priced combo quote should carry its read age and mark its own verdict
   stale.** n = 1: the same ticker went ask 302 → 329 tenths, depth 2928 → 152,
   verdict "+0.3% EV. Rare" → "−7.9% EV. Don't." in forty minutes. Justified on
   cost asymmetry, not on n. **It relabels, it never blocks** — disabling the
   buy control is a new ceiling on a hand bet and ADR 0112 forbids it.
5. **`Freshness` is gated `stale === 0 || unbuilt === 0`** and would go silent
   on a pool empty because nothing was ever fetched — the one state that most
   needs it. Unobserved; a conjecture from reading, worth one test that builds
   that pool.
6. **NFL prop fixture capture** (`KXNFLANYTD`, `KXNFLFIRSTTD`, a yardage
   series). One unauthenticated `/events` pull, capture only. Bottom; drop first.
7. **The combo fee-model reopen trigger** (n = 68) — standing no. Unchanged.
8. **`pip-audit` pyarrow ignore**, **the binned card** — unchanged.

**Joe-gated: the `/parlays` lede's final wording** ("hardly anyone" vs "rarely
anyone" vs his own). Everything else in the correction is correctness and
shipped without asking.

**Two contamination notes for whoever reads these instruments next.** Four
`desk_attention` POSTs at 13:50Z and 14:01Z were an AGENT, not Joe — they are
in this week's dwell record and `visit-freshness` will count them as visits.
And `parlay_lookups` rows 47–58 are agent taps, twelve of them, all on
2026-09-10.

### Lessons written

Two, both pattern-level: **a stopping rule that names an outcome manufactures
that outcome**, and **an operation that reads can also write — "it spends no
money" is not the test for whether it is inert.**

## 2026-09-10 (seventh session) — a combo tap now prices the window the card was built in, and the desk has a spreads-only card Joe chose

**Found by doing what Joe did.** He tapped "Buy it on Kalshi" on a "Through
tomorrow" card at 22:22 PT and every leg was refused as "started, or past
tonight's last game". None had started. The lookup was pricing every card at
`tonight` whatever window built it, guessing the reason, and writing no row.
Kalshi minted for future games all along (fixture minted 5 days out, live id
2 priced a next-day leg): the refusal was ours.

**STATE at close.** `main` = **`158a90c`**, pushed, **CI green
(run 34447293327)**; full suite on main before the docs commit: **6870 passed,
10 xfailed, 0 failed** (10m29s). **Live = `158a90c`, schema v38,
machine `7812601a239428` unchanged** (deploy run 34448064455;
migration v37 -> v38 at boot in under a second (07:04:26Z, both log lines carry the same second; backend healthy after 13 s, health passing 07:04:49Z)). Demo untouched. Odds path
untouched: the freeze to 10:00Z 2026-09-14 holds; `git diff 324a53f..main --
backend/odds backend/scheduler.py` is empty and `fly.live.toml` changed only
in comment lines.

Two ADRs: **0138** (a lookup prices the window the card was built in; a
refusal is recorded, schema v38; the sentence never guesses; the copy says
who quotes a combination), **0139** (Two short spreads is a rule Joe chose).
One registration: `docs/measurements/2026-09-10-preregistration-totals-market-credit-cost.md`.
Three lanes ran in parallel worktrees, all merged, worktrees and branches
removed. Eight reviewer agents ran before the plan (partner, two explorers,
kalshi-platform twice, sharp-bettor, measurement-skeptic, pre-registrar);
Joe answered three lettered questions in one line: recipe **A**, keep all
six cards, write the registration.

### THE HEADLINE: the horizon now travels with the tap — ADR 0138

`POST /api/parlays/lookup` takes `horizon` (validated against `HORIZONS`
with the GET's own 422 words), `price_card_on_kalshi` passes it to
`ladder_candidates`, and the screen sends the ladder payload's `window.key`
from `ParlayCards` through `PriceOnKalshi` to `lookupParlay`. An absent leg
is now classified from the sportsbook's own kickoff: "has started" only when
`commence_ms <= now`, "kicks off after the '<window words>' window ends —
pick a wider window" when beyond the horizon, "is not a leg this desk
serves" otherwise. **Schema v38** rebuilds `parlay_lookups` so `status`
admits `'refused'`, and the resolve step records the refusal (legs, horizon,
the words) before re-raising; the `book_empty` branch now writes the YES
side and both level counts into `error`, so an empty NO side is no longer
indistinguishable from an empty book. Copy: "Kalshi itself almost never has
anyone selling this combination" and "Nobody has offered this price" are
gone — Kalshi quotes the minted combination itself (a resting NO bid is the
ask you pay, 33 of 40 books carried one); nobody bids to buy it back, so the
exit is the outcome. "Try again shortly" is gone too: **0 of 6 repeat groups
on live ever flipped from empty to quoted, out to 80 minutes.**

**A merged query was corrected the same hour, and it is the lesson in
miniature.** Lane 1's kickoff lookup LEFT JOINed a `GROUP BY odds_event_id`
over all of `odds_snapshots` — `MATERIALIZE o`, `SCAN odds_snapshots` on
every refused tap, the plan `CANDIDATE_SQL` was measured at 15 s with on
2026-08-26. It is now a correlated scalar subquery seeking `idx_odds_event`,
the statement is a function the plan test imports, and
`tests/test_ladder_query_is_indexed.py` pins plan and value.

**Rehearsed in the container on the real rows before the deploy**: the
exact statements from the new `db.py` against a scratch file holding the
live table's 42 rows (attached `mode=ro`, nothing copied but that table):
digest identical through forward, replay, undo and forward again; the old
CHECK refuses `'refused'`, the new one accepts it; the index survives;
2 ms. No 5 GB copy this time, on purpose — see the lesson below.

### The recipe — ADR 0139

`short_spreads` / "Two short spreads": `markets={"spreads"}`,
`max_spread_margin=3.5` (a new `Recipe` knob; a spread's `point` is the
book's number and always negative, so the bound is on `-point`),
`min_legs=max_legs=2`, likeliest-first, one leg per fixture from
`_best_per_game`. Not pushed to the phone. The leg row now shows a kind tag
("SPREAD −3.5", "WIN", "PROP <line>") from `leg.market`/`leg.point`, which
were on the wire and never drawn; `spread` joined the glossary.

**Census before the build, read off live at 06:10Z (48h window):** 14 spread
legs, **9 at 3.5 or shorter across 6 fixtures** (MLB 1.5/2.5 runs, NFL and
NCAAF 3.5), `p_conservative` 0.33–0.57, odds 34–48 min old because no page
was open. Every one was `stale_consensus` on the route at that hour, which is
the feed on its hourly floor, not a defect.

**Its Kalshi quote rate is unmeasured and the prior is unfavourable**: on
live, **0 of 11 lookups containing a spread leg came back quoted, against 12
of 28 moneyline-only** — self-selected taps, confounded with league and date
(the 11 include every NCAAF row and mostly six-leg cards), so a correlation
and not a mechanism. The falsifying pair is one lookup of this card and one
of a moneyline card on the same slate in the same minute. Not yet taken.

### Focus 2 decided, most of it by the record rather than by Joe

- **Totals: not this season at `us,eu`.** The multiplier is exactly 1.5
  (`sweep_cost = markets x regions`), and the largest budget day on record
  (496, 2026-09-05, no NFL) becomes **744 against 700**. **ADR 0110 already
  refuses totals** and dates the only lever (drop `eu`, 3 credits a call) to
  2026-09-28 behind two preconditions. Below the feed, totals do not exist:
  no series constant, no subtitle parser, not in the runner's derived link
  set, no pricing branch, not in `CANDIDATE_SQL`. The credit look is
  registered (§0 gate: totals have no consumer — already true; one look after
  10:00Z 09-14 on budget day 20260913; edges 560 / 700 fixed).
- **NFL props: undiscovered.** `PROP_SERIES` is MLB-only, zero `KXNFL*` prop
  rows on live, and FIRSTTD/ANYTD carry no strike so the props join has
  nothing to join on. Needs one unauthenticated `/events` capture before any
  parser is written against memory.
- **MLB props are dead on live** — last `fair_prices` write 2026-08-16, 0
  rows in 24h. Not a recipe source.
- **Long ladder and Longshot stay** (Joe's answer). The sharp-bettor's
  argument that their only distinguishing feature is more legs, and legs are
  hold, is on the record for the next UI ticket.

### Verified by disabling

    Lane 1 horizon pass-through      1 mutation   2 tests red
    Lane 1 started/after-window fork 1 mutation   4 red
    Lane 1 refused status            1 mutation   1 red
    Lane 1 book_empty detail         1 mutation   2 red
    Lane 2 margin filter             1 mutation   1 red
    Lane 2 spreads-only markets      1 mutation   1 red
    main   kickoff query plan        the merged query itself was the red case

### Still open, in order

0. **THE FALSIFYING PAIR FOR THE SPREAD CARD.** One lookup of "Two short
   spreads" and one of a moneyline card, same slate, same minute, read off
   `parlay-lookups-tail`. Until then the card's Kalshi quote rate is a prior,
   not a measurement. **Taken once at 07:09Z after the
   deploy, and it did not separate anything**: `short_spreads` (NYY −1.5,
   LAR −3.5) and `safe` (three moneylines, all on the 10th and 11th) minted
   within four seconds of each other and BOTH came back `book_empty` with
   `yes_levels=0 no_levels=0` (rows 45 and 46; 43 was the same safe card a
   second earlier). A pair where both sides are empty is consistent with
   "spread combos are never quoted" and with "nothing is quoted at 00:09 PT
   on a future-game combo".

   **THAT STOPPING RULE WAS WRONG AND IT WAS FOLLOWED — 2026-09-10, eighth
   session.** It read "take it again when a moneyline card is quoted", which
   conditions the retake on one arm's outcome. Taken under it at 13:51Z, the
   moneyline arm came back 2 of 2 quoted **by construction of the rule, not
   by observation**, and the tap order shows the mechanism: three moneyline
   taps, then the spread tap last, once the trigger was satisfied. The
   resulting "clean separation" is uninterpretable and was withdrawn the same
   session. The honest accounting of this test is **two pairs taken, one null
   (07:09Z, BOTH arms empty), one outcome-conditioned (13:51Z)** — and the
   first is the one that counts.

   **The replacement rule, unconditioned:** tap the moneyline card and the
   spread card **in a fixed order within the same minute, on a schedule fixed
   in advance** (18:00Z daily for five days), and record **every** pair
   including the ones where both arms come back empty. Five unconditioned
   pairs are worth more than the 48 rows now on the table. Do not start it
   before Sunday's Arm D look — every lookup mints a market into that
   measurement's own sampling frame (see
   `docs/measurements/2026-09-10-disclosed-unregistered-look-combo-exit-shard1.md`).

   **And a confound that no number of pairs can settle**, found by
   `measurement-skeptic` the same session: `lookup` **creates** the market
   when the combination does not already exist
   (`backend/kalshi/combos.py`), and the spread-bearing recipes (`lottery`
   at 6 legs, `longshot` = the three *least* likely games, `short_spreads`)
   are exactly the combinations no human would have built in the Kalshi app.
   So "spread combos are not quoted" and "**self-minted tickers** are not
   quoted" predict identical data, and `parlay_lookups` records no
   pre-existence flag. Add that column before running the pairs, or the
   pairs cannot separate the two. Evidence already against the second story:
   two shard-1 books minted at 13:43:30Z and 13:45:34Z carried resting YES
   bids when read from ~13:46Z, so a *fresh* mint can be two-sided within
   three minutes.

   The mint, not the tap, is the unit: **no minted ticker in the whole
   record has ever changed status between reads**, including one re-read
   across 6h44m, so repeat taps of a ticker carry zero information and the
   row denominator (31/17) is inflated. At the mint denominator it is 13 of
   26 moneyline-only against 0 of 11 spread-bearing — a correlation, still
   not a mechanism, and it does not survive matching on leg count (3 legs:
   9/17 vs 0/4).
   **The tap Joe asked for is verified on live**: under "Next two nights"
   the safe card (NCST, LOU on the 11th, NYY on the 10th — every leg beyond
   tonight) minted `KXMVECROSSCATEGORY-SHARD1-…AC3CA136377` and answered
   `book_empty` in 2.4 s (row 43); the same legs under "tonight" answered
   409 "kicks off after the 'games kicking off before tonight's slate ends'
   window ends -- pick a wider window" and wrote row 44, `status =
   'refused'`, `horizon = tonight` on every leg. Attention registered at
   07:08:14Z and the consensus was fresh by 07:09:18Z. Small gap seen in the
   rows: a `book_empty`/`priced` row's legs carry no `horizon` (only the
   refused branch adds it) and no `side`/`label` on this path — read
   `legs_for_position` before relying on either.
1. **DO NOT TOUCH THE ODDS PATH BEFORE 10:00Z ON 2026-09-14.** Unchanged.
   After it: the registered totals look, and the `window_status` covering
   index candidate (unchanged).
2. **SUNDAY 2026-09-13 — a scheduled run, not a task to plan.** Unchanged.
3. **The cold-cache cost of the ladder query is 75 s.** Measured this session
   in the container: `ladder_candidates` at `tomorrow` took **74.8 s** on a
   page cache a research agent had just flushed with two full-table
   `GROUP BY`s over `fair_prices`, then **2.15 s** warm; `/api/parlays`
   answered 503 `read_budget_exceeded` at 25 s on both windows in between.
   The read budget (ADR 0135) held. Not a regression — see the lesson — but
   it is the number a first tap after any full-table read will pay.
4. **The boot health grace is 600 s.** Unchanged.
5. **`position_state` has not fired on live.** Unchanged.
6. **The combo fee-model reopen trigger** (n = 68) — the partner's standing
   no: a constant that cannot change a decision does not get a session.
7. **`pip-audit` pyarrow ignore** — trigger only, unchanged.
8. **The binned card** — do not rebuild, unchanged.

**Joe-gated: NOTHING.** All three questions were answered in-session.

### Lessons written

One, pattern-level: a read-only full-table scan on live evicts the page
cache, and the next reader pays for it — a census goes through the indexed
path the product uses or a bounded key range, a 503 at the read budget
minutes after a live read is the read and not a regression, and a subagent
told to read "read-only" will still flush the cache unless the instruction
bounds the rows.

**And one about my own procedure.** I merged a lane whose query I had not
run `EXPLAIN` on, and it carried the exact plan this repo had already
measured and fixed once. The plan test existed for the sibling statement;
the new statement was not held to it until I looked. A new query against a
growing table gets its plan pinned in the same commit that introduces it.

## 2026-09-10 (sixth session) — the ladder floor was OOM-cycling the recorder; the fix shipped, and /hedge now says what it cannot see

**Found by measuring the thing the last entry said was slow, from the outside,
before touching it.** Item 0 said the 9-day floor scanned 6.5M rows and
`/api/parlays` paid it twice. It was worse: the scan's `ROW_NUMBER()` runs
under `temp_store = MEMORY`, so 6.5M rows became ~1 GB of resident memory in
BOTH processes, and the 2 GB box had restarted three times in five hours
before this session began. The partner's ranking and the sharp-bettor's craft
review both redirected the hedge-alert ask to coverage first, and the coverage
read was 0 of 1.

**STATE at close.** `main` = **`324a53f`** plus this entry, pushed; **CI green
on `324a53f` (run 34437142296)**; full suite on main before the docs commit:
**6845 passed, 10 xfailed, 0 failed** after one timezone fix. **Live =
`324a53f`, schema v37, machine `7812601a239428` unchanged** (deploy run
34437560202; migration `v36 -> v37` at boot in 172 s). Demo untouched. Odds
path untouched: the freeze to 10:00Z 2026-09-14 holds, and `credits-day` shows
no attention row during either probe — a server-side fetch of an SSR page does
not register attention, only the client's `/desk-attention` POST does.

Four ADRs: **0134** (the ladder scan keys on the confirmed stamp; v37 partial
index), **0135** (an abandoned request stops executing; `API_READ_BUDGET_MS`),
**0136** (the hedge screen says what it cannot see), **0137** (the phone says
which legs are live, on a schedule — amends ADR 0078 D2 on Joe's word). Six
lanes ran in parallel worktrees, all merged; worktrees and branches removed.

### THE HEADLINE: the box was dying every hour, and opening `/parlays` could kill it on demand

`docs/measurements/2026-09-10-the-ladder-floor-oom-cycles-the-recorder.md`.

Timed from outside with a minted read-only cookie (the MCP Chrome tab group
carried no session cookie, so no browser-side paint timing exists — say so if
you cite this): `/api/window`, `/api/signal`, `/api/parlays`, `/api/slate` all
**500 at exactly 30 s** (Next's rewrite-proxy timeout; uvicorn keeps executing
after Next hangs up, so abandoned queries pile up), `/parlays` unanswered at
180 s. Three minutes later the kernel killed the runner at **1.13 GB** and then
uvicorn at **1.88 GB**, and the machine rebooted. The runner's own log
(`loop-rss`) had carried the attribution since the v36 deploy at 22:52Z:
RSS **196 MB -> 1.10-1.23 GB** per pass, `candidate_ms` **83 -> 3,549-9,454**,
over the same ~440 rows; boot lines at 00:32Z, 01:04Z, 03:18Z; a
`PassDeadlineExceeded` at 23:33Z. Nobody had read that column.

**The fix, and why not the obvious one.** Narrowing the floor back was ruled
out by item 0 itself. The predicate now reads
`(f.computed_ms >= ? OR f.confirmed_ms >= ?)` — exact, because a confirmed
stamp is never older than its frozen one — served by a **partial** index
`idx_fair_market_confirmed ON fair_prices(market, confirmed_ms DESC) WHERE
confirmed_ms IS NOT NULL`, which holds **614 rows** on live. The plan is a
`MULTI-INDEX OR` with two seeks; with the index dropped the `computed_ms>?`
term vanishes and the existing plan test goes red. The 9-day constant is gone;
the floor is `max(8 x max_odds_age_ms, 2h)` again. Rehearsed in the container
on a paced copy: the index build reads the whole 10.1M-row table once,
**181.8 s cold**, so the boot health grace went **120 s -> 600 s** with the
measurement beside it in `fly.live.toml` (the container's image cannot
pre-build an index its code does not know). Live built it in 172 s.

**After, on the warm box:** `/api/parlays` **1.1 s**, `/api/slate` 0.6 s,
`/api/board` 0.27 s, `/api/hedge` 0.13 s, every SSR page under 2.2 s; the
runner at **189 MB, 72-75 ms** over 434 rows; zero OOM lines since. The
first post-boot reading had `/api/window` at 20 s — that was the cold page cache
after the reboot and the 5 GB rehearsal copy, not a second defect: replayed on
live it is **0.95 s**, 0.91 of it one `GROUP BY` over `odds_snapshots`.

Two independent brakes shipped beside the query fix, on the partner's ruling
that their failure modes differ from the query's: the runner **builds the
ladder only when a card could be sent** (`Alerter.parlay_cards_could_send`,
so the change-alert debounce still advances on real builds), and every
per-request API connection carries a **25 s progress-handler budget** that
answers 503 `read_budget_exceeded` instead of piling up behind a proxy that
already gave up (`API_READ_BUDGET_MS`, under Next's 30 s).

### The hedge screen covered 0 of 1 live positions, and now says so

Read off live at 03:25Z: the venue held ONE open combination (17.74 contracts,
$9.69) bought in the Kalshi app, absent from `parlay_positions`; the one
recorded position (id 1, the $1.64 BOS/NYY/LAD combo) had **settled `no` at
01:40Z** in `venue_settlements` while still reading `open` with three
`pending` legs, because `resolve_from_venue` reads only `kalshi_markets.result`
and the venue had not finalized the leg markets (and the result pass runs
inside the full pass that kept dying). ADR 0136: `/api/hedge` now carries
`unrecorded_at_venue` (KXMVE tickers in the latest **ok** positions poll with
no open row — the membership-of-latest-complete-observation rule), per-position
`at_venue` and `venue_settlement`, and the screen renders the quote age beside
every leg price (it was in the payload and never drawn). No auto-close: which
leg lost is not knowable from the combo's settlement. Verified on live after
the deploy: position 1 renders `dead`, `at_venue: false`, settlement `no`, BOS
`lost`, NYY `won`, LAD `pending`; the venue list is `[]` because the $9.69
combo settled between 03:25Z and 04:41Z (`row_count 0`).

### The push Joe chose — ADR 0137, amending ADR 0078 D2

Asked which push he wanted, Joe chose the **symmetric "legs in play"
statement**: once per ticket per budget day when a watched game is in play,
every pending leg's venue bid with its quote age, "N of M legs live", the
sentence "No figure locks" when N > 1, the lock figure only when N = 1 and one
exists, `not_advice` and `upper_bound` verbatim, record order, the parlay
colour. **Identical template on a good day and a bad day** — the sharp-bettor's
argument that carried it: an alert that fires only on bad news is a nudge by
construction; one that fires on a schedule carries no information in its
arrival. Kind `position_state`, key `position_state:{id}:{day_start_ms}`, own
ceiling of 4/day, own counter. A forbidden-words test pins the transport. The
watcher spends nothing metered (existing test still green). **Not yet observed
firing on live** — no position was in play after the deploy.

The sharp-bettor's other findings, recorded for the next UI ticket, not built:
the de-risk headline (a joint built on the unmeasured 0.05/0.02 correlation
nudges) is the least defensible number on the page and should go; the
five-column ladder does not fit a phone at the moment of decision (contracts,
cost, worst case; the two branches behind a tap); no total exposure line; the
combo's own live quote and the absence of a resting YES bid are never shown.

### Verified by disabling

    Lane A runner gate       3 mutations   3 red (7 tests)
    Lane B v37 predicate     3 mutations   3 red   + one vacuous test rewritten before it could pass for nothing
    Lane C read budget       2 mutations   2 red
    Lane D coalesce          1 mutation    1 red
    Lane E1 coverage facts   5 mutations   5 red   + one isolation test added when a mutation showed two clauses untested apart
    Lane E2 the push         4 mutations   4 red

### Still open, in order

0. **A COMBO TAP REFUSES EVERY FUTURE-GAME CARD, AND LEAVES NO RECORD.** Joe's
   screenshot, 22:22 PT 2026-09-09: the "Through tomorrow" SAFE card (NYY,
   LAR, PHI, all kicking off on the 10th) tapped "Buy it on Kalshi" and got
   "these legs cannot be priced right now ... no longer on the desk's slate
   (its game has started, or it is past tonight's last game)" for all three.
   Cause, from the code: `POST /api/parlays/lookup` carries no `horizon`
   (`backend/api/schemas.py` ParlayLookupRequest), the route calls
   `price_card_on_kalshi` without one, and it re-runs `ladder_candidates` at
   `DEFAULT_HORIZON = "tonight"` (`backend/parlays.py`, `price_card_on_kalshi`
   -> `ladder_candidates(conn, now_ms=..., max_odds_age_ms=...)`), so any leg
   past 4am is absent from the pool and `resolve_requested_legs` refuses it
   with a sentence that guesses "started". The refusal is raised BEFORE
   `_record_lookup`, so `parlay_lookups` has no row for it (live still ends
   at id 42, 2026-09-09 15:12Z). Also stale: the card copy "Nobody has
   offered this price" / "almost never has anyone selling this combination"
   — Kalshi quotes the minted market itself (6 of the last 8 lookups
   `priced`, 2 `book_empty`); the entry/exit conflation ADR 0078's amendment
   corrected. Prompt for the session that fixes it is in the 2026-09-10
   session's closing message and repeated here in short: carry `horizon`
   from the ladder through the request to the lookup and validate it against
   `HORIZONS`; record a refused lookup; make the sentence say what is known;
   correct the copy; ask kalshi-platform what decides `book_empty` on a
   minted combo. **Read on live 2026-09-10 05:5xZ, for the fix and for what
   Joe asked next:** `combo_eligible_events` (3,648 rows, refreshed
   04:36Z) spans 26SEP09..26SEP21 (1,016 legs on 26SEP12, 357 on 26SEP13),
   so "Next two nights" is inside Kalshi's own combinable window and the
   only refusal was ours; and the list already carries `KXNFLSPREAD` (142),
   `KXNFLTOTAL` (142), `KXNCAAFSPREAD`/`KXNCAAFTOTAL` (118 each), NFL
   props (FIRSTTD 110, RSHYDS/RECYDS/PASSYDS 97, ANYTD 94). Joe wants
   spreads, totals and props in parlays. What blocks it: `ODDS_MARKETS =
   "h2h,spreads"` (`fly.live.toml:486`, odds path, frozen to 10:00Z
   2026-09-14, and the multiplier is exactly 1.5 (`sweep_cost = markets x
   regions`, `backend/odds/budget.py:66-68`, 4 -> 6 at `us,eu`), ADR 0110
   already refuses totals this season because the largest budget day on
   record (496 credits, 2026-09-05, no NFL) becomes 744 against the 700 cap,
   and the only lever that admits totals is dropping `eu` (3 credits a
   call), dated 2026-09-28 behind ADR 0110's two preconditions; the credit
   look is registered in
   `docs/measurements/2026-09-10-preregistration-totals-market-credit-cost.md`);
   `CANDIDATE_SQL` admits h2h, spreads and five MLB prop keys only; the
   four `CARD_SHAPES` recipes pick "the N likeliest games", one leg per
   fixture (same-game stays out, ADR 0012 section 5). A recipe is a rule
   Joe chooses, never a ranking by edge (ADR 0071).

1. **DO NOT TOUCH THE ODDS PATH BEFORE 10:00Z ON 2026-09-14.** Untouched. One
   candidate for after the freeze, measured not decided: `window_status`'s
   `GROUP BY odds_event_id` over `odds_snapshots` costs ~0.9 s and is polled
   every 10 s by `RefreshWhenPriced` while a tab is open; a covering index
   would be the shape, and it needs its own re-timing.
2. **SUNDAY 2026-09-13 — a scheduled run, not a task to plan.** Unchanged.
3. **The boot health grace is 600 s.** Raised for v37 on a measurement; the
   file's own rule says raise rather than trim a migration to fit. Lower it
   only with a reason, not by reflex.
4. **`position_state` has not fired on live.** The first in-play watched
   position will tell; check `notifications WHERE kind = 'position_state'`
   after it, and that `hedge_lock` still fires separately.
5. **The combo fee-model reopen trigger** (n = 68) — unchanged, Joe-gated
   whether it gets a session; the partner asks that any session name the
   constant it could move before it starts.
6. **`fly.live.toml` growth-rate copy (old item 6) — ALREADY CORRECTED** in
   an earlier edit (`:668-670` records the 326.6 MB/day realisation). Closed.
7. **`pip-audit` pyarrow ignore** — trigger only, unchanged.
8. **The binned card** — do not rebuild, unchanged.

**Joe-gated: NOTHING.** The one question this session (which push) was
answered in-session.

### Lessons written

One, pattern-level: the cost of a scan is not its wall-clock — under
`temp_store = MEMORY` a window function turns rows read into resident memory,
so a floor widened for a correct reason is re-timed on live reading RSS beside
milliseconds before it ships; and an abandoned request is not a finished one.

**And one about my own procedure.** I measured the live site with a probe that
was, functionally, a user opening four tabs, and the box died three minutes
later. The probe was right to run and the death was going to happen at Joe's
next tap either way — but a measurement that can take the box down is one to
announce before running, and to run one route at a time.

# The session index

Every session entry ever written to this file, newest date first. Full text in
the linked archive file, unchanged.

### Split 2026-09-11 — [`archive/next-2026-09-11.md`](archive/next-2026-09-11.md)

Filed by the date of the split. The five 2026-09-09 and two 2026-09-08
entries that were still in `NEXT.md` when it reached 200,701 bytes, 76.6%
of the ceiling. Taken **under** the trigger rather than at it, before the
session's own entry was written, because the entry about to be written was
a long one and the size that matters is the size *after*. Cut deep, to
37.2%. The cut falls on a date boundary: everything 2026-09-09 and earlier
moved, so no single day is split across two files. Verified by md5: the
archived bytes below its header hash identically to the bytes removed
from `tasks/NEXT.md`.

- 2026-09-09 (fifth session) — the biggest table in the database is 99.7% duplicate rows, and the obvious fix would have emptied the ladder
- 2026-09-09 (fourth session) — a live bet was invisible to the only screen that could exit it, and the wiring that fixed that killed the question a registration was asking
- 2026-09-09 (third session) — the desk armed the entry and never armed the exit; and the census behind every combo warning had never read the shard he trades
- 2026-09-09 (second session) — the audit file is closed after 33 days, the money-path signer finally has a real test, and the fee alarm was wired the day its own excuse expired
- 2026-09-09 — two critical unauthenticated RCEs were live on the public box and are now patched; the effort dial is set; the month-old audit is down to two real items
- 2026-09-08 (third session) — the fat was cut: CLAUDE.md is 20KB, six agents are gone, four task files are archived, seven lessons deduplicated
- 2026-09-08 (second session) — the table took its first two rows, the brake Joe removed was still on the button, and the bid path is disarmed

### Split 2026-09-08 (second) — [`archive/next-2026-09-08-second.md`](archive/next-2026-09-08-second.md)

Taken for readability rather than size (ADR 0116): the three closed
entries from 2026-09-07 and the first 2026-09-08 session, each carrying a
`Still open` list the entry that stayed supersedes. Verified by md5
(`e8c041c54a1b0d17bb8b54908c8204d7`).

- 2026-09-08 — Joe corrected what the desk is FOR at the moment of a bet, and the four things stopping him turned out to be ours
- 2026-09-07 (second session) — tonight's check had no instrument on the box and the wrong reading written down; attention was paying a live-game cadence for a line two days out
- 2026-09-07 (earlier session) — the NFL path is pre-flighted and its first sweep is due tonight by construction; a failed look and a spent day get their own words; the watcher stops asking the venue about a bid that filled

### Split 2026-09-08 — [`archive/next-2026-09-08.md`](archive/next-2026-09-08.md)

Filed by the date of the split. The six 2026-09-06, one 2026-09-05, one
2026-09-04 and two 2026-09-03 entries that were still in `NEXT.md` when it
reached 205,381 bytes, 78.3% of the ceiling. Taken **under** the trigger
rather than at it, at Joe's instruction, before a fresh session started —
and cut deep, to 22.3%, so the next several sessions need not think about
it. The cut falls on a date boundary: everything 2026-09-06 and earlier
moved, and no single day is split across two files. Verified by md5: the
archived bytes below its header hash identically to the bytes removed
(`823e72d9643035f974168e24d26b440c`).

- 2026-09-06 (sixth entry) — the published credit bound was a partial sum, item 3 was half-false, and the largest NFL day-one risk is a failure nobody had timed
- 2026-09-06 (fifth entry) — the parlay window became a control, the in-play combo question is answered, and props are a feed problem rather than a venue one
- 2026-09-06 (fourth entry) — Joe took the offer-making controls off the desk, and what replaces them is a record of a bet placed somewhere else
- 2026-09-06 (third entry) — the partner ran first and its top item was not on the list; the credit answer was refused once before it was kept; three lanes landed and the inspector stopped blocking work
- 2026-09-06 (second entry) — Joe answered the four open questions; the combo note now carries BOTH censuses, ADR 0085 has Amendment 1, PRs #1/#2 are closed, and the shard-3 test and the key rotation are DROPPED on his word
- 2026-09-06 — the parlay census is TAKEN and ADR 0085 is REFUTED at the moment Joe buys; #24, Lane A2, the money-arm predicate, the agent wire fixture and Joe's four answers are all deployed; the inspector blocks work at 99.3%
- 2026-09-05 — the session Joe stopped is picked up: three finished lanes merged (ADR 0106, 0107, the routes split), and the one cross-lane break git could not see
- 2026-09-04 — six lanes landed (ADR 0104, 0102 Amd 1, the Read-ceiling guard); the presence measurement was registered, taken once, audited, and is UNRESOLVED — CONCENTRATION; the partner killed #11's log form; five questions for Joe
- 2026-09-03 (second entry) — the partner found the desk had not gone quiet and the /picks heal was switched off; three lanes landed (ADR 0101–0103); one question and one rotation for Joe
- 2026-09-03 (early) — the partner reordered the queue around a regression shipped the day before; three lanes landed; Joe answered the second batch

### Split 2026-09-06 — [`archive/next-2026-09-06.md`](archive/next-2026-09-06.md)

Filed by the date of the split. The three 2026-09-02, two 2026-09-01 and four
2026-08-31 entries that were still in `NEXT.md` when it reached 223,790 bytes,
85.4% of the ceiling. Taken before the session's entry was added rather than
after, and cut deeper than the trigger required so the cut falls on a date
boundary: everything 2026-09-02 and earlier moved, and no single day is split
across two files.

- 2026-09-02 — the partner ran first; P5 is terminated, #6 is built, and the desk went quiet
- 2026-09-02 — one deploy became nine commits, because the instrument was never on the box and then was wrong
- 2026-09-02 — four lanes landed, the volume had 16 days left, and a wizard died of the defect it was written to prevent
- 2026-09-01 — the lock holder is attributed, the partner had never been invoked, ticket #11 is resolved, and a $100 money stop turns out to be unable to fire
- 2026-09-01 — open item 4 named an instrument that cannot see the failure it measures, and the good news I wrote off it was refused
- 2026-08-31 — the sweet spot reaches all three surfaces, and a second opinion convicted a four-month-old number
- 2026-08-31 — the lock holder was found, and a wording rule lost to typography
- 2026-08-31 — the sweet spot, and the graph Joe asked for
- 2026-08-31 — the Scout reaches the parlay legs, and the budget says it can only flag them

### Split 2026-09-05 — [`archive/next-2026-09-05.md`](archive/next-2026-09-05.md)

Filed by the date of the split. The five 2026-08-30 and two 2026-08-29
entries that were still in `NEXT.md` when it reached 224,305 bytes, 85.6% of
the ceiling. Taken before this session's entry was added rather than after.

- 2026-08-30 — the deadline the screen promised had never once been kept
- 2026-08-30 — the desk placed its first real order, and the venue has no one to fill it
- 2026-08-30 — the WAL read was taken, it could not run, and the memory level halved
- 2026-08-30 — the positions payload was observed, a refusal became a record, and two lanes closed two backlog items
- 2026-08-30 — the hour-long silences are a poisoned connection, and the ticket takes dollars
- 2026-08-29 — the signal test could never have answered its own question, and twelve lanes landed
- 2026-08-29 — THE READ WAS TAKEN, and every gap turns out to be a container death

### Split 2026-09-01 — [`archive/next-2026-09-01.md`](archive/next-2026-09-01.md)

Filed by the date of the split. The seven 2026-08-28 entries that were
still in `NEXT.md` when it reached 85.6% of the ceiling. Taken before
the session's entry was added rather than after.

- 2026-08-28 — the read was attempted a second time, the window survived, and it is 8 minutes old
- 2026-08-28 — the pre-registered read was taken, and it was not a read
- 2026-08-28 — PRE-REGISTRATION: how to read tomorrow's gap, decided before the data exists
- 2026-08-28 — the unexplained gap was the sixteenth, and nothing on disk could have said so
- 2026-08-28 — a leg priced at zero stopped the alerting half of the loop, and the heartbeat fired for a DIFFERENT reason
- 2026-08-28 — one tab could take the site down, and the desk went quiet without saying so
- 2026-08-28 — the palette split shipped, and the guard watching it was measuring the wrong pair

### Split 2026-08-31 — [`archive/next-2026-08-31.md`](archive/next-2026-08-31.md)

Filed by the date of the split. The 2026-08-28 and 2026-08-27 entries that
were still in `NEXT.md` when it reached 87.3% of the ceiling. Taken before
the session's entry was added rather than after.

- 2026-08-27 — the map got three rulings and a colour, and this file learned the map exists
- 2026-08-27 — the alarm that watches for a silent death had been taught to fire every day, and the combo tests were all in the wrong branch
- 2026-08-27 — two lanes can be seen at once, and the tool that saw them told a human to delete sixteen projects
- 2026-08-27 — a cold open buys odds on the pass it woke
- 2026-08-27 — the parlay push stops being a race and becomes a schedule

### Split 2026-08-29 — [`archive/next-2026-08-29.md`](archive/next-2026-08-29.md)

Filed by the date of the split. The 2026-08-26 and 2026-08-25 entries that were
still in `NEXT.md` when it reached 86% of the readable-size ceiling. Taken at
86% rather than 98.9%, on the rule the previous split wrote.

- 2026-08-26 — three commits had no entry, and one of them raised the bet
- 2026-08-26 — the live box was OFF between visits, and five commits later the desk draws pictures
- 2026-08-26 (hedging lane) — the desk starts watching what Joe already holds, and a hedge turns out to need no model at all
- 2026-08-26 — the buy control reaches every card, and the ticket renders on a real book for the first time
- 2026-08-26 — one parlay generator becomes six, and the notifier is deliberately left behind
- 2026-08-26 — the alarm stops guessing, and the desk's cards reach the phone
- 2026-08-25 — the desk was empty because the loop was ASLEEP, and nothing could wake it
- 2026-08-25 (later) — the odds feed stops watching the clock and starts watching whether anyone is there
- 2026-08-25 — the declaring look is REFUSED, and §P4 turns out to have been an opt-in nobody opted into

### Split 2026-08-27 — [`archive/next-2026-08-27.md`](archive/next-2026-08-27.md)

Filed by the date of the split. The 2026-08-24 through 2026-08-20 entries
that were still in `NEXT.md` when it reached 98.9% of the readable-size
ceiling.

- 2026-08-24 (fifth session, close) — SUPERSEDED by the entry above: the screen's declaration did not survive audit
- 2026-08-24 (fifth session) — the purpose gets settled, and the feed is told to follow attention
- 2026-08-24 (fourth session) — the parlay desk earns a nav slot and every game names its sport
- 2026-08-24 (third session) — the desk is used for real, and a combo book is populated for the first time ever
- 2026-08-24 (second session) — all 14 review findings fixed, and the repeat tap turns out to be idempotent
- 2026-08-24 — code review of the parlay-desk session: 14 findings (ALL FIXED — see the entry above)
- 2026-08-23 (third session) — the parlay desk: three cards at fair value, spreads priced, and the combo's real cost one tap away
- 2026-08-23 (second session) — the desk presents fully: likely winners on the slate, five areas per game, Willy's seat
- 2026-08-23 — the desk window opens: the slate stops being stale 14 hours a day
- 2026-08-22 (third session) — the pass gets its caller, the probe gets cheap to start, and stale odds get an exit
- 2026-08-22 (second session) — the every-page review ships whole: kill list, glossary, real limits, and a manual door built dry
- 2026-08-22 ~13:15Z — the betting-desk list closes out: CLV on his own bets, then the ticket cleanup
- 2026-08-21 ~23:30Z — the landing screen stops claiming an edge, and the session hands off
- 2026-08-21 ~22:45Z — the refusal lands on real data, and the lockout gets the desk's name
- 2026-08-21 ~21:45Z — /bets ships, and the partner re-rules the refusal work by name
- 2026-08-21 ~20:30Z — the desk gets a token meter and a nav slot in one change, and the gold goes out
- 2026-08-21 ~18:30Z — Joe rules the purpose, the Skeptic retires, and the cost record gets honest
- 2026-08-21 ~16:45Z — the market screen joins the shell, and the desk scales to a real instrument panel
- 2026-08-21 ~15:30Z — the briefing becomes a cockpit, and the market screen serves the venue's facts
- 2026-08-21 ~06:30Z — the Scout desk is switched on, on Joe's word: a staff of two and a master, metered
- 2026-08-21 ~04:30Z — the replay gate passes exactly, and the ledger's null kickoff is fixed
- 2026-08-21 ~03:15Z — the H4 series closes on a measured reason: the channel diagnostic is BLIND on a denominator of 1
- 2026-08-21 ~02:00Z — h4-balance-spans ships with its guards red, and both deploys landed
- 2026-08-21 ~00:20Z — H4 Look 1 is taken and moves nothing, tomorrow's terminal spread look is armed, and one deploy waits on Joe
- 2026-08-20 ~21:35Z — the spread test is TAKEN: UNDERPOWERED both arms, and the partner's list is the open work
- 2026-08-20 ~19:45Z — the dropouts are diagnosed, the zero is verified, and the spread test is armed for 21:21Z
- 2026-08-20 ~17:00Z — the gate is measured, the product has a plan, and a slice is built but NOT deployed

### Split 2026-08-25 — [`archive/next-2026-08-25.md`](archive/next-2026-08-25.md)

Filed by the date of the split rather than of the entries, like the 08-18 file
below it: these are the 2026-08-19 and 2026-08-17 entries that were still in
`NEXT.md` when it reached 93% of the readable-size ceiling.

- 2026-08-19 ~23:20Z-00:30Z — THE FIXES HELD FOR 2H40M, NOT 12 HOURS; AND THE UNMATCHED QUEUE'S OBVIOUS FIX WAS AN OUTAGE
- 2026-08-19 ~16:20Z — THE 15:21Z TEST WAS TAKEN; THE STORE LEG IS INNOCENT, AND THE FLAPPING WAS NEVER THE BACKEND
- 2026-08-19 ~12:15Z — ADR 0053 HALF-HELD; THE COST MOVED TO THE STORE LEG, AND I GUESSED WRONG ABOUT IT FIRST
- 2026-08-19 ~02:30Z — LIVE HAS BEEN FLAPPING ALL DAY, I SAID IT WAS HEALTHY, AND THE CAUSE IS THE QUOTE PASS
- 2026-08-19 ~late — THE STRIP IS ON THE PHONE, BY JOE'S CALL
- 2026-08-19 ~mid — THE STRIP SAYS WHERE THE NUMBER CAME FROM, AND THE DEMO WAS DISAGREEING WITH ITSELF
- 2026-08-19 ~early — THE ALARM WAS WATCHED, AND THE CODES SPEAK ENGLISH ON FOUR SCREENS
- 2026-08-17 21:55Z — THE MEASUREMENT IS NOT DUE YET, AND THAT IS THE WHOLE SESSION
- 2026-08-17 — JOE'S THREE ITEMS, AND THE LANE THAT WAS BRIEFED WAS THE ONE THAT DID NOT EXIST
- 2026-08-17 — THE MORNING WARNING WAS ARITHMETIC, AND IT IS GONE FROM THE LIVE SCREEN
- 2026-08-17 — THE INSTRUMENTS NOW DISAGREE WITH THE MACHINE OUT LOUD
- 2026-08-17 — THE PRODUCT NOW STATES WHAT ITS CONCLUSION IS WORTH

### 2026-08-18 — [`archive/next-2026-08-18.md`](archive/next-2026-08-18.md)

- 2026-08-18 ~night — THE ALERTS LEAVE THE PHONE, AND THE FAILURE CHANNEL IS WIRED
- 2026-08-18 ~evening — THE DESKTOP TIER EXISTS, AND THE GREEN-ZERO DEFECT DIED FIRST
- 2026-08-18 ~16:30Z — THE TRIAGE IS DISCHARGED: THE STOP HAS A READER, THE BANKROLL IS DERIVED, AND THE COMBO FEES GOT THEIR REGISTERED LOOK
- 2026-08-18 11:10Z — THE STUDY IS OPEN, THE MACHINE MATCHES ITS COMMIT, AND THE PARTNER HAS SET THE ORDER
- 2026-08-18 08:50Z — THE ENTRY FORM EXISTS, AND THE DATABASE ITSELF NOW REFUSES TO EDIT AN ESTIMATE
- 2026-08-18 08:30Z — THE POLLER IS LIVE, AND JOE'S OWN RECORD IS NOW MIRRORED WHERE KALSHI CANNOT DELETE IT
- 2026-08-18 00:30Z — THE PUBLIC DEMO OVERSTATES SIZE BY 17x, AND THE ADR THAT CLOSED THAT HOLE CANNOT SEE IT

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
