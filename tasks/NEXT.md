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

**Split again 2026-08-25, at 243,486 bytes — 93% of the ceiling, not past it.**
The 08-19 and 08-17 entries moved to `archive/next-2026-08-25.md`, verbatim,
leaving ~146KB here. Waiting for the test to go red is the wrong trigger: the
test guards the *file*, and what actually breaks first is the instruction at the
top of it — a session that cannot read the whole file reads the head and
silently believes it has the state. **Split at ~90%, not at 100%.**

**Split again 2026-08-29, at 225,270 bytes — 86%, before writing anything.**
The 2026-08-26 and 2026-08-25 entries (9 of them) moved to
`archive/next-2026-08-29.md`, verbatim, leaving ~148KB here. This is the first
split taken on the rule rather than on the alarm: `wc -c` was read before the
session's entry existed, and the entries moved out before it was added.

**Split again 2026-09-05, at 224,305 bytes — 85.6%, checked before writing.**
The five 2026-08-30 and two 2026-08-29 entries moved to
`archive/next-2026-09-05.md`, verbatim, leaving ~166KB — 63.6%. Taken under
the trigger rather than at it, because the entry about to be written was a
long one and the size that matters is the size *after*. The index section
went in the same edit; a split that moves entries without moving their index
lines is a data loss with a table of contents.

**Split again 2026-09-06, at 223,790 bytes — 85.4%, checked before writing.**
The three 2026-09-02, two 2026-09-01 and four 2026-08-31 entries moved to
`archive/next-2026-09-06.md`, verbatim, leaving 117KB — **44.7%**. Cut deeper
than the trigger required, on the reasoning `archive/lessons-2026-08-31.md`
records: clearing to well under the line buys one more split rather than
several. The cut falls on a **date boundary** — everything 2026-09-02 and
earlier moved — so no single day is split across two files, which the previous
splits did not always manage and which makes the index harder to read than it
needs to be. The move was verified by md5: the archived bytes below its header
hash identically to the bytes removed. Index lines moved in the same edit.

**Split again 2026-09-08, at 205,381 bytes — 78.3%, well under the
trigger and on Joe's instruction rather than on the rule.** The six
2026-09-06, one 2026-09-05, one 2026-09-04 and two 2026-09-03 entries
moved to `archive/next-2026-09-08.md`, verbatim, leaving **58KB — 22.3%**.
The deepest cut this file has taken, and deliberately so: it was asked for
before a fresh session opened, which is the one moment the cost of cutting
too much is zero and the cost of cutting too little is a split mid-session.
Date boundary as always; md5 verified; index lines written in the same
edit.

**Split again 2026-08-27, at 259,407 bytes — 98.9%, and that is a miss.** The
2026-08-24 through 2026-08-20 entries (27 of them) moved to
`archive/next-2026-08-27.md`, verbatim, leaving ~140KB here. The rule above says
90% and it was not followed, because the entry that crossed the line was the one
being written and nobody checks the size before adding. **Check `wc -c` BEFORE
writing an entry, not after** — at 98.9% the margin was 2,737 bytes, roughly one
paragraph, and the failure mode is silent.

---

## SESSION START — if Joe said "read NEXT.md", this box is your prompt

Repo: `C:\Users\josep\Documents\Claude\Projects\kalshi_betting_tool`,
branch `main`. Check `git status` and `git log origin/main..main` rather than
trusting any sentence here, and read the LIVE instance's `/api/health` for its
`git_sha` — it sits under `build`, not at the top level. The calibration study
is STOPPED (2026-08-20, Amendment 2; the recorder machinery still runs). Joe is a beginner and has
asked to be educated: define every betting/stats term at first use, via
`frontend/src/lib/glossary.ts` and `<Term>`.

**The test count is CI's, not a hand-collected number. Retired 2026-09-01.**
`.github/workflows/ci.yml` runs `ruff check .` and `python -m pytest -q` on
every push to every branch, free, under a 15-minute cap. Read the last green
run: `gh run list --limit 5`.

**What was deleted here, and why it is not a loss.** This spot held ~87 lines
reconciling a hand-collected suite count across trees. It documented **seven**
occasions the number was wrong in the same direction, plus four runs killed
mid-flight -- and every one of those corrections was honest and was spent on a
figure whose only consumer was the paragraph itself. The rule it taught
survives and is worth more than the number: **do not reconcile a baseline by
reasoning about a delta; collect both trees.** Apply it to any count you do
take. Run targeted tests locally while you work; let CI collect the total.

**The suite is ~15-22 minutes and growing with the record.** A slow run is not
a hung one, and neither is a gap the length of an interval. If it gets slower,
look for a test doing real work to check a cheap property -- one took 71
seconds driving a 200,000-sample copula to assert a dictionary length.

**Two things to know before planning. CLAUDE.md is current on both:**

1. **The signal test has NOT declared. The 2026-08-24 `NO SIGNAL` was
   refused on audit, 2026-08-25.** The verdict is **UNRESOLVED at G = 216**
   — the registered primary is the modal `strategy_config_version` alone
   (§P4/§7), and `G = 311` was a fit pooled across four versions. Fixed in
   code the same day. Full audit:
   `docs/measurements/2026-08-25-clv-signal-declaring-look-refused.md`.
   **The direction is unchanged and still settled for planning** — every
   interval at either look sits entirely below the 0.40 threshold.
2. **What the tool is FOR is settled — ADR 0071.** A personal betting desk
   first; price transparency as the job; a gap you may show on a row and
   never rank by; sharing means someone runs their own copy. Read it before
   planning anything, and do not re-derive the purpose.

**TWO OTHER LANES ARE RUNNING. Check them before you plan anything**, because
main is not the whole picture:

    git worktree list

They live under `~/.herdr/worktrees/kalshi_betting_tool/` and are Herdr's, not
this session's — nothing here starts or stops them.

**There is no longer a hand-maintained table here, and that is the fix.** The
one that stood in this spot said `parlay-props` was "0 ahead, 1 behind, one
uncommitted file"; within hours it was 0 ahead, **10** behind, with **15**
dirty files, and `hedging-research` had merged and been removed. A hand-typed
lane state asserts the present tense and starts rotting the second it is saved.
Read the generated board instead:

    .venv\Scripts\python.exe scripts/lane_board.py

It reads every worktree and local branch at once — ahead/behind, uncommitted
work, ADR and schema claims, and which files two trees are changing at
overlapping *hunks* rather than merely in the same file. `tasks/LANES.md`
carries the last written snapshot plus the **allocation ledger**: what a live
lane has said it will take before it exists on disk, which is the one thing no
measurement can produce.

**They have collided with main three times in one day, and git said nothing
about the ones that mattered.** From `hedging_research`'s own commit messages:
*"the hedging ADR becomes 0077, because 0074 was taken twice and git said
nothing"*, then *"becomes 0078 — 0077 collided too"*, then *"two lanes both
claimed schema v23, and the hedge tables take v24"*. Each was caught by a human
reading a merge.

`tests/test_parallel_lanes_do_not_collide.py` fails on a duplicate ADR number,
and `scripts/lane_board.py` now sees the other lanes *before* a merge —
including their uncommitted work, which no test can reach, because a test only
sees the tree it runs in.

**But do not claim a number by reading either one.** `tasks/lessons.md:168-191`
settled that: reading `main` first answers "what was free when I looked", and a
lane that runs for hours races every other lane for the whole of it. Write the
ADR as `docs/adr/DRAFT-<slug>.md` with **no ordinal** and take the number in
the merge commit, after `git fetch`, as the last thing before the push. The
guard refuses a `DRAFT-` file on `main`, which is what makes that unavoidable
rather than merely encouraged. Full rule: `docs/adr/README.md`.

**`docs/adr/0006-*` is NOT a collision.** `0006-in-play-evidence.md` is the
companion to `0006-in-play-scope.md` and shares its number on purpose. The
guard keys on what a document's H1 *claims to be*, not on its filename, for
exactly this reason — and that exemption is pinned, because a guard whose first
finding is a false one gets deleted.

**THE UI WORK IS NOT IN THIS FILE. It is a decision map on GitHub, and until
2026-08-27 nothing here said so.** `/wayfinder` charts one map issue with child
tickets; ours is **#3 "Cockpit for the pilot"** on `josephsapinoso/kalshi-cockpit`,
7 resolved and 23 open. Every screen question — what "Picks" opens, what each
tab is for, the colour system, what the list filters by — lives there with its
evidence, and a session that plans UI from this file alone **will re-derive
decisions Joe has already made**. Read the map body first (it is the low-res
index; the detail is in the closed tickets, fetched on demand):

    gh issue view 3 --json body --jq .body
    gh api repos/josephsapinoso/kalshi-cockpit/issues/3/sub_issues --paginate       --jq '.[] | select(.state=="open") | [.number,(.assignee.login // "-"),(.issue_dependencies_summary.blocked_by // 0),.title] | @tsv'

The second command is the **frontier query**: open, unblocked (`0`), unassigned
(`-`), first in map order wins. Conventions are in `docs/agents/issue-tracker.md`
(committed 2026-08-28; it was untracked and one `git clean` from gone). Claim a
ticket by assigning it to yourself BEFORE any work, and **resolve exactly one
per session** (research tickets excepted). The map produces *decisions*, not
builds: it is done when nothing is left to decide before someone builds it.

**THIS FILE IS THE FRONT DOOR, NOT THE MAP — asked and answered by Joe,
2026-08-28.** He asked directly whether a new session should start from
`/wayfinder` or from here. It starts from **here**, always; the map is one of
the queues this file points at. Two facts a session needs:

- **A session cannot invoke `/wayfinder` at all.** Its `SKILL.md` sets
  `disable-model-invocation: true` — Joe types it or it does not run. What a
  session *can* do alone is read the map with the two `gh` commands above, and
  that is what the paragraph above is for. Do not sit waiting to invoke it.
- **There are THREE queues and this file used to name two.** The "Open" list at
  the end of the latest entry is repo and infrastructure work. The map's open
  tickets are *decisions to be made*. The third is **decided and not yet
  built** — a closed ticket carrying a spec — and it belonged to nobody,
  because the map's own rule is to produce decisions rather than builds. **A
  resolved ticket with a build attached is a NEXT.md item.** That gap is not
  theoretical: ticket #10 was resolved at 03:34Z on 2026-08-28 recording a WCAG
  failure on the live real-money confirm button, and under the old reading no
  queue owned it.

So: read `git status`, then this file's Open list, then the frontier query —
in that order. The frontier query is the third read, not the default lane.

**THEN INVOKE THE `partner` AGENT, BEFORE PLANNING ANYTHING.** It owns what
gets worked on, in what order, and by whom. **Until 2026-09-01 nothing in
this repo told a session to do that** -- `CLAUDE.md` did not mention the
partner at all and this box did not name it -- so every session re-derived
its own priorities from a 140KB file and worked one item. Joe asked why the
partner was not involved every session, which is how it was found. It is
now `CLAUDE.md` workflow step 0. Hand it the state (what is open, what
landed, what is blocked) and ask for a ranked list AND which items can run
as parallel lanes. Skip it only for a single errand Joe named himself.

Read `CLAUDE.md`, then the latest entry below (it is the whole brief), then
`tasks/lessons.md` top two. Re-verify state, never inherit it:

    .venv\Scripts\python.exe -m pytest -q     (NEVER bare python; PATH is 3.14)
    cd frontend && npx tsc --noEmit

Expected: the number above, ruff clean, tsc clean, `next build` green.
Check `/api/health` `git_sha` against `origin/main` before assuming anything
is live. The terminal spread/total look was **VETOED by Joe 2026-08-21
16:11Z**, recorded per §7.1 in
`docs/measurements/2026-08-21-spread-total-edge-second-look-result.md` —
nothing fires at 22:40Z and no session needs to be alive for it. **The H4 look series is CLOSED
— BLOCKED ON INSTRUMENT, 2026-08-21** — do not build the A9–A12 analyzer
and do not re-run the channel diagnostic (A17.6/A17.11).

## 2026-09-08 (second session) — the table took its first two rows, and the brake Joe removed was still on the button

**STATE at close.** `main` = **`a13e6b8`**, pushed, CI green. **Live is on
`a13e6b8`, verified off `/api/health` `build.git_sha` at 21:33Z**, machine
`7812601a239428` **unchanged** across every deploy today — check that after any
deploy, because a new machine gets an empty volume and every credit fact
inverts silently. Re-read `/api/health` rather than believing this table.

    live     a13e6b8 verified 21:33Z; recorder writing, age 41s; mode live
    demo     cc8de80 deliberately behind, untouched today

Four commits landed and **all four are deployed**:

| sha | what |
|---|---|
| `ebbb809` | the exposure ceiling comes off the hand-bet path (ADR 0112 Amd 1) |
| `68cabc4` | the buy button agrees with the route (ADR 0114) |
| `272f328` | the `source` steer removed from seven surfaces (P2) |
| `a13e6b8` | four ADRs corrected; the depth guard now reads `docs/adr/` |

Tree clean at close, no worktrees. Suite **6495 passed / 10 xfailed** — the
jump from 6369 is mostly the depth guard's parametrize now globbing every ADR,
plus 14 hand-written tests.

### THE FINDING: `manual_orders` is no longer empty

Read off the live box with `inspect_live_db.py manual-orders-audit`, which is
structure-and-counts only by design:

    n_rows 2   real_orders 2   dry_runs 0   with_kalshi_order_id 2
    distinct_tickers 2         status: filled 2
    19:41:07Z and 19:42:07Z, 2026-09-08
    3 contracts and 4 contracts
    both KXMVE combinations, both on shard 1
    manual_order_refusals: 0 rows

**The table had never held a row of any kind in the 14 days it was armed.**
NEXT.md's previous entry named this as the thing that would be genuinely new,
and it happened within hours of ADR 0112 removing the four brakes and check 9a
naming the shard. **Item 2 of the previous Open list is struck.**

**ADR 0113's inference fired as written.** It replaced "he does not want to
transact here" with "the door had something wrong with it", and predicted that
fixing the door was what to try. Two fills and zero refusals, the same evening.
**Do not over-read it**: `n = 2`, one sitting, one evening. It is a census
count, not a test, and needs none — the interesting property is that the
number stopped being zero, which is a fact about the door and not an estimate
of anything.

**Both are on shard 1, which is the funded pocket** ($22.24 against $0.00 on
shard 0). So he bet the path his money was already in, which is exactly what
check 9a exists to tell him. **Whether to fund shard 0 is still Joe-gated and
still unanswered** — and note it is now a real constraint rather than a
hypothetical: singles remain unbuyable until he moves money.

### The brake he removed was still on the buy button

Found while checking whether ADR 0112's "no ceiling of ours bounds a hand bet"
was actually true on the deployed box. It was true of the route and **false of
the screen.**

`GET /api/manual/market/{ticker}` served `authorised_contracts` from
`min($3.00 spend cap, 10% of the observed balance)` — both removed by name —
and `ManualTicket.tsx` disables Confirm above that number. **On a 90c market it
authorised 3 contracts against a route that would take 250.**

Three consequences from the one root, and the second is the ugly one:

1. Two 422s on the money path said *"what bounds the BET is the $3.00 spend
   cap, checked below."* Nothing was checked below.
2. `authorised_contracts` was `None` when the balance had never been observed
   — rendered as a refusal. **`ebbb809` made POST accept that state, so this
   session's own earlier commit WIDENED the mismatch** it was part of closing.
3. The ticket called every bound *"your per-bet cap"*, by then the one thing
   none of them was.

**This is the repo's named failure a fourth time — one predicate with two
spellings — and the first time it ran this direction.** The three earlier
instances were a screen promising buying that was not happening. This one
refused betting that was permitted, on the only path that spends real money.

Fixed: the count is now the structural ceiling, the depth at the ask and what
the market's shard can pay for — the three bounds the POST route applies to
size, so the two agree by construction rather than by hand. `authorised_binding`
is new on the wire and the ticket says which one bit, in plain words, because
waiting for the book and moving money between shards are different remedies.
`ADR 0114`; take the ordinal in the merge
commit after `git fetch`.

**Two tests had preserved the error rather than catching it** — one asserted
`"spend cap"` PRESENT in the combination refusal, one asserted `"your per-bet
cap, not your typed amount"` present in the ticket. Both green every day the
copy was false; the same shape `backend/parlays.py:105-111` records about
`"40 of 40"`. Both re-pointed to pin the dead phrase absent, neither deleted.
Verified by disabling: restoring the old bound turns 5 of the 7 new tests red.

### Still open, in order

1. **DO NOT TOUCH THE ODDS PATH BEFORE 10:00Z ON 2026-09-14.** Unchanged, and
   nothing this session went near it. Frozen surface:
   `backend/odds/{timing,budget,attention,ondemand,client,sweeplog}.py`. After
   10:00Z on 09-14: `credits-day --date 20260913`, `sweep-log`,
   `visit-freshness`, and split the mechanisms off `odds_sweep_log.detail`,
   **NOT** `api_credits.trigger`. A deploy is not contamination; logic changes
   are.
2. ~~`RecordParlay.tsx` defaults `source`.~~ **DONE, same session.** No
   default, not a flipped one: the initial state is `""`, `<option value="">
   Choose one</option>` is selectable rather than merely initial, the submit
   button is disabled without a choice AND `submit` refuses one (a form can be
   sent from the keyboard, and `""` reaches the server as a 422 he cannot act
   on). `ParlayCards.tsx` no longer hard-codes the value and its copy no
   longer calls a book slip the first-class path. **Precondition P2 is met and
   the clean window opens at this deploy.**
   **The "no frontend test framework" risk was real and is now covered** —
   `tests/test_recording_a_bet_is_reachable.py` reads the source text, and one
   of its existing assertions had been *requiring* the steer (`assert 'source:
   "sportsbook"' in source`). Four guards now, all verified red by restoring
   the steer.
   **THE CLEAN WINDOW IS OPEN. It opened `2026-09-08T21:33:05Z`** — looked up
   from deploy run `34281066870`, per P4, and recorded in the registration's
   Appendix A with the machine id beside it. **Do not census before P1 and P3
   also hold**: P1 needs an accepted ADR recording the entry design (ADR 0113
   is the correction that motivated P1, not the design document it asks for)
   and P3's denominator script does not exist. Earliest legitimate deletion
   read is `G = 30` sittings after this timestamp, backstop 2026-11-30.
3. ~~The combo entry/exit conflation is still in four ADRs.~~ **DONE, same
   session.** `0073`, `0070` and `0075` (two places) carry correction notes
   quoting what they replaced; **none of their decisions moved**, because
   every one rested on the EXIT claim and only the entry reasoning was wrong.
   `0078` got an amendment saying it was audited and *survives* — its
   sentence named entry and exit separately and got both right — recorded so
   the next session does not re-audit it.
   **The guard now reads the decisions, not just the code.** `PINNED` globs
   `docs/adr/*.md`, so a new ADR is covered the day it is written, and
   `FORBIDDEN` gained the conflation itself (`"it is rarely live"`,
   `"3 of 20 and 3 of 9"`) — previously only the depth figure was guarded, so
   the half that reached a screen was unguarded. 132 tests. Both verified by
   planting the claim in an unmarked ADR.
   **One limitation found and written into the guard rather than left to be
   discovered:** a correction note's strike marker shields its own paragraph,
   so the one place a struck claim can quietly return is beside its own
   correction. Re-inserting the depth phrase into ADR 0070's corrected
   paragraph left the suite green. That is the accepted cost of keeping wrong
   text verbatim; narrowing the window already failed on CLAUDE.md's real
   shape.
4. ~~`FiveStepTest.tsx` names the retired Log tab.~~ **DONE, same session.**
   Now: *"Find the market from Games, open its buy ticket, and type your
   P(YES) before you look at the price"* — which is the path that exists, and
   the ticket really does mask the ask until the estimate is typed. The
   sentence about a form asking whether he had already opened Kalshi went with
   it: no such question exists. `ManualTicket.tsx:274` handles the anchored
   case by SAYING the number is anchored and recording it anyway.
5. **`window_status` cannot predict a bootstrap** — FROZEN until 09-14
   (`timing.py:1536`).
6. **The `eu` lever, 2026-09-28** — ADR 0110's measurements first; three of the
   four are free and takeable now. **Its `exchange_index` deferral is closed,
   2026-09-08.** That section named its own overturning condition — *"if the
   manual route is ever used on a non-zero shard, this section is where the
   work starts"* — and the condition fired: both of tonight's first-ever
   `manual_orders` rows are on **shard 1**. Two of its three killing facts are
   spent (the "0 of 27 real bets" is the stale-negative shape; the 420-market
   `exchange_index: 0` capture was of NFL SINGLES when the reachable case was
   always combinations), and the work was built independently hours earlier as
   check 9a. The ADR carries the correction. **Nothing to build; the `eu`
   decision itself is untouched and still dated.**
7. **Scout Anthropic refusal fixture (ADR 0106 §5.2)** — one billed call. NOT
   dead code: `routers/scout.py:25` imports `agents.scout_desk`.
8. **`combo_orders` — CLOSED. He said "disarm the bid path" and it is
   disarmed (ADR 0115).** The findings that produced the question are kept
   below because the reasoning behind a disarm is what a re-arm has to answer:

   - **Nothing is resting.** All five bids `combo_orders` has ever held are
     terminal: four `cancelled` ("the first leg has started"), one
     `gone_at_venue` (id 2, placed 09-01, resolved 09-07 — the venue had no
     order by that id, so it filled, was cancelled or settled; the desk does
     not know which and cannot without account data). **The previous entry's
     "a pre-09-06 bid may still rest" is resolved: none does.**
   - **Zero UI callers, confirmed.** No `.tsx` imports `placeComboBid`,
     `cancelComboBid` or `listComboBids`. The `api.ts` helpers, the
     `/parlay-bid` proxy route and its middleware entry all still exist.
   - **It is armed**: `COMBO_ORDERS_ARE_DRY_RUNS = False` since 2026-08-30,
     on Joe's own words *"the exchange is done. arm the switch."*
   - **It is NOT under-guarded, and an audit that said so was wrong.** The
     route has no `is_demo` check of its own, which looked like CLAUDE.md's
     "one config bug from the order path". It is not: `require_auth` refuses
     on `is_demo` before reading a token and the route depends on it. The
     arming discipline is *equivalent* to the hand-bet path's — mode plus a
     deliberate switch — the switch just being a constant rather than an env
     var, which `combo_orders.py` argues for in its own words. **A guard was
     written for this and reverted.** What survives is
     `TestTheDemoCannotRestABid`, which pins the property on the endpoint that
     spends money rather than only on `require_auth`'s own test; verified red
     by deleting the demo branch.

   **The question that was put to him, and his answer.** This
   endpoint exists to REST OFFERS, and on 2026-09-06 he asked for the
   offer-making controls to be removed — *"I don't want to make offers or find
   offers in shares"* — a ruling CLAUDE.md records as **still standing** as of
   2026-09-08. The UI was removed; the armed real-money endpoint was not.
   Three options were put to him — disarm, delete, or leave armed — and he
   chose **disarm**. Done, one line, in a commit of its own, the procedure the
   constant's own comment specified. The switch's interlock test went red on
   the flip exactly as it was written to, and the acknowledgement is in its
   docstring.
   `COMBO_ORDER_MAX_SPEND_TENTHS` ($3.00) is deliberately **not** touched: it
   binds nothing while the path is dry, and it is the ceiling that would apply
   on re-arming. Raising it while nobody is watching is how a removed cap
   comes back by accident.
9. **The decision map's third queue is two items, not nine.** A full audit of
   all 32 closed tickets against the tree finds 23 built, 7 decided as "no
   build", 2 genuine gaps — one of which is item 4 above. The "~9" was carried
   forward without re-measuring.

**Joe-gated, two questions, both stated fully in the items above:**

- **(A)** Fund shard 0 so single-market bets work? Shard 1 (Combos) holds the
  money; shard 0 (Default) is at $0.00, so every single-market bet dies at the
  venue. Check 9a now names the pocket and the reallocation link rather than
  letting it read as a broken cockpit.
- ~~**(B)** `POST /api/parlays/bid`.~~ **ANSWERED: *"disarm the bid path."***
  `COMBO_ORDERS_ARE_DRY_RUNS = True`, ADR 0115. The route, table, watcher and
  cancel path all STAY — a dry run still writes the row and still says
  "Nothing was sent to the exchange" — and **deleting it was one of the three
  options and is not what he chose.** Do not finish the job by removing it as
  dead code.

### The pattern worth carrying (goes to `tasks/lessons.md`)

The previous entry's Open list had **two** items stale in the same way. Item 2
said "there is not one yet" about a thing that happened an hour later; item 9
said "~9 live items" about a queue drained to two. Neither was wrong when
first written; both were copied into a new entry without being re-read off the
instrument.

**A count or a "not yet" copied forward into a new session entry is an
assertion about the present tense made from a past reading.** This file already
learned it about lane tables — *"a hand-typed lane state asserts the present
tense and starts rotting the second it is saved"* — and the Open list was
exempt by nothing but habit. Every numeric or negative claim in a `Still open`
list should carry the command that produced it, or be re-run when the entry is
written.

---

## 2026-09-08 — Joe corrected what the desk is FOR at the moment of a bet, and the four things stopping him turned out to be ours

**STATE at close.** `main` = the sha in `git log -1`, pushed; read CI with
`gh run list --limit 3`. **Live was ON main twice today** and verified both
times off `/api/health` `build.git_sha`, not off a sentence — but this entry
was written before its own commit, so **re-read `/api/health` rather than
believing the table.** The last verified pair was `95fbe16` on both, at which
point this entry's own commits (ADR 0113 and the NEXT.md entry) were not yet
made and are docs-only.

    live     95fbe16 at last verify; machine 7812601a239428 UNCHANGED both deploys
    demo     cc8de80 deliberately behind, untouched today

**Check the machine ID after any deploy.** Every pacing quantity for the odds
budget is a SQL read against `api_credits` on the mounted volume; a NEW machine
gets an EMPTY volume and every credit fact inverts silently. It was
`7812601a239428` before and after both of today's deploys.

Tree clean, no worktrees, decision map still 0 open. Suite **6369 passed / 10
xfailed** before the last two commits; re-run at the top of the next session
rather than trusting this number.

### The correction that reordered the whole day

Joe, unprompted, mid-session: **when earlier work said "sportsbook", he meant
KALSHI'S sportsbook.** He does not want a control for logging bets placed at a
third-party book. He wants to **place bets on Kalshi through the cockpit
directly — single markets and combinations both.**

That contradicted ADR 0105 at its premise, and the 2026-09-06 write-up of his
"both" answer was a misreading. **The offer-making half of that ruling stands**
— no resting bids, no "shares", pay the ask.

### What was actually stopping him, and none of it was the venue

`manual_orders` had **0 rows of any kind** after 14 days armed. ADR 0105 read
that as "he does not want to transact here". Five defects say otherwise, all
found today:

| | |
|---|---|
| per-bet cap | **~$2.14** — 10% of a ~$21 balance, while he had been told the cap was $3.00 |
| daily-loss switch | the **same** ~$2.14, counting losses from bets placed in the Kalshi APP |
| cool-off | 10 minutes against a measured ~2.3 fills per sitting |
| order token | 43 characters retyped from scratch on every bet |
| shard check | **absent entirely** — zero references to `exchange_index` on the path |

**ADR 0112** removes the first four on his word. He was re-asked on two after
being shown a consequence the first framing omitted, and did not move: that the
per-bet cap and the daily switch are the SAME number, and that the typed token
was the **credential**, not merely friction, so a person holding his unlocked
phone can now bet his money. §4 states the consequence in one sentence and §5
reserves restoring any of it to Joe. **Do not restore these on your own
judgement.** The re-pointed tests are *inverted*, not deleted, so a restored
brake fails loudly.

**The total-exposure ceiling (40% of balance) went too, later the same day.**
It was left standing for a few hours precisely because he had not been asked
about it, then he was asked: *"remove the exposure ceiling too."* **ADR 0112
Amendment 1.** `reserve_manual_order` no longer takes `max_exposure_dollars`
and cannot raise `ExposureCapExceeded`; check 6 refuses nothing and survives
only to derive the figure the recorded row carries; an unobserved balance no
longer refuses, because refusing on a precondition for a guard that no longer
exists is how a removed cap comes back by accident.

**So no ceiling of ours bounds a hand bet at all.** What remains is the desk
lockout, idempotency, the KXMVE acknowledgement, the price ceiling, depth at
the ask, the netting guard, the shard collateral check (the VENUE's rule), the
structural contract ceilings, and reserve-then-check. `orders.reserve_order`
still caps the ENGINE — same scoping as ADR 0112 §3.

**Two things did NOT go with it and are about reading, not capping:**
`current_manual_exposure_dollars` is still computed and reported, and an
exposure that cannot be READ still rolls the transaction back. The atomicity
test was re-pointed onto that surviving refusal rather than deleted.

### His shard allocation inverted the advice, and the desk could not see it

Read off Kalshi by Joe: **shard 1 (Combos) $22.24, shard 0 (Default) $0.00.**

So **combos are the funded path and single markets are the blocked one** —
the reverse of what was being said all day. And the manual path had no shard
awareness, so every single-market bet would have died at the VENUE with a bare
`insufficient_balance`, which against a $22 account reads as a broken cockpit.
ADR 0084 solved this for combinations and the reasoning was never carried
across; `combo_orders.check_affordable`'s own docstring says why — only the
desk is in a position to say so.

Check 9a now refuses first, naming the shard, the shortfall, the reallocation
link, and — deliberately — **"This is the venue's rule, not a cap of yours."**
A refusal he reads as a cap sneaking back is worse than no refusal.

- The shard is read **off the market** (`exchange_index`, new on
  `DiscoveredMarket`, exposed on `LiveQuote`), never from the ticker prefix:
  Kalshi calls that field authoritative and says ticker formats move. A test
  pins `"KXMVE"` ABSENT from the check.
- Unreadable refuses **both ways**: no `exchange_index` refuses rather than
  guessing 0 (**0 is a real shard**), and an unparsable balance refuses rather
  than resolving to spendable. `_exchange_index` rejects a bool explicitly —
  `True` is an `int` and would become shard **1**, the combinations shard.
- The balance is read **scoped**. The unscoped call returns the SUM and can pay
  for nothing: $21.41 total beside $0.01 on the shard that needed it,
  2026-08-30. That payload is now a test.

### ADR 0113 supersedes 0105, by 0105's own mechanism

§5 named two overturning conditions "and nothing softer"; the second was **"Joe
saying so."** It fired as written.

**The census is retained, not withdrawn.** Still 0 of 27, still true. Only the
*inference* is replaced — from "he does not want to" to "the door had something
wrong with it". A count of zero through a door with five defects measured the
door. 0105's inference is recorded as **underdetermined, not careless**: the
five were not enumerated until today.

**Two kills are NOT refunded**, and §4 says so explicitly: ticket #11's
estimate log form (he spoke about placing bets, not logging estimates;
question D is still unanswered and still governs) and
`/api/estimates/last-scored` (its source is structurally empty regardless).
**Do not read the supersede as a refund.**

**§6 sets a trap worth knowing about:** a future census of 0 may NOT overturn
0113 unless it first establishes the path was usable across its whole window,
dated from today's deploy. Otherwise it is the same measurement read the same
wrong way, twice.

### The combo depth figure on the refusal screen was false three ways

`"the deepest resting bid ever measured here was 18 units, so a larger count
could not fill"` — shown to Joe inside a 422, citing ADR 0012 §5.

1. **The citation is spurious.** ADR 0012 has no depth figure; its only `18` is
   the denominator of `same-game 17/18`, a rate it withdraws itself.
2. **The scope was dropped.** The real source says "the deepest resting order
   **here** was 18.00 units" — one run of 11 rows. Every copy promoted "here"
   to "ever measured".
3. **Repo-wide it is wrong by ~38x.** The committed captures carry resting NO
   bids of **683, 413, 369, 311, 309, 300**.

**And entry was being reported backwards.** `PriceOnKalshi.tsx` told him to
"expect it to refuse" off `3 of 20 and 3 of 9` — those are the `volume` counts,
rows that had ever **traded**. The resting-bid counts are 16/20, 6/9, 11/11:
**33 of 40**, five books in six, each a hittable offer. The code was fine
(check 8 reads `depth_at_ask`, the NO-bid depth); only the words were wrong.

**What survives is the exit:** zero resting YES bids over 36 levels on 40/40.
`tests/test_combo_book_depth_claims.py` pins the arithmetic to the capture
files. Its phrase guard permits a correction note that quotes what it replaced
and refuses a fresh assertion — the window reaches **forward** as well as back,
because a correction often opens with the phrase it is striking.

### The 09-15 `parlay_positions` deletion clause is VACATED

Not deferred — it fires on no date. The entry form **defaults `source` to
`"sportsbook"`**, the option Joe has now disowned, and the steer runs on seven
surfaces; `ParlayCards.tsx:257-261` **hard-codes** it. **The number of days a
neutral choice was shown is 0.** A 0 on 09-15 could not separate "hedging is
unwanted" from "logging someone else's slip is unwanted".

Splitting by `source` was **rejected** — it fixes which-book and leaves the
steer. The power check kills it independently: no denominator at all, and
supplying one gives `G ≈ 9-16`, a one-sided 95% bound of 0.19-0.33.

One verdict-free census is permitted on/after 09-15, usable ONLY as a planning
`n`. A deletion decision needs a successor registration gated on four
preconditions, observing `G = 30` sittings or 2026-11-30.
`docs/measurements/2026-09-08-parlay-positions-check-amendment-registration.md`.

### Still open, in order

1. **DO NOT TOUCH THE ODDS PATH BEFORE 10:00Z ON 2026-09-14.** Sunday 09-13 is
   the only attended NFL Sunday this month and the one live term of the credit
   convergence is whether the attention slice binds. After 10:00Z on 09-14:
   `credits-day --date 20260913`, `sweep-log`, `visit-freshness`, and **split
   the mechanisms off `odds_sweep_log.detail`, NOT `api_credits.trigger`**,
   which pools them and is displaceable by the schedule.
   **Frozen surface:** `backend/odds/{timing,budget,attention,ondemand,client,
   sweeplog}.py`. **A DEPLOY IS NOT CONTAMINATION** — the pacing quantities are
   re-read from the mounted volume every pass, verified empirically (the
   03:44:05Z restart bought zero credits). Logic changes are.
2. **The first real `manual_orders` row is the finding**, and there is not one
   yet. When one lands, that is genuinely new: the table has never held a row
   of any kind. Do not census it before then and do not read a continued 0 as
   evidence — ADR 0113 §6 forbids exactly that without first showing the path
   was usable.
3. **`RecordParlay.tsx:69-70`** still defaults `source` to `"sportsbook"`, and
   `ParlayCards.tsx:257-261` still hard-codes it. Flip to **no default**, not a
   flipped one. This is precondition P2 of the successor registration and the
   clean window opens at its deploy — **do not delay it to protect
   continuity**, the window is already void.
4. **ADR 0078's justification needs rewriting even though the feature
   survives.** "Combos are enter-only, so a leg hedge is the only exit" rests
   on the entry/exit conflation corrected today. The hedge survives on the
   EXIT claim, which is untouched.
5. **`window_status` cannot predict a bootstrap** — FROZEN until 09-14
   (`timing.py:1536`).
6. **The `eu` lever, 2026-09-28** — ADR 0110's measurements first. Three of the
   four are free and takeable now.
7. **Scout Anthropic refusal fixture (ADR 0106 §5.2)** — one billed call. NOT
   dead code: `routers/scout.py:25` imports `agents.scout_desk`.
8. **`combo_orders` reconciliation** — re-scope. `POST /api/parlays/bid` is a
   **live, armed, real-money endpoint with zero UI callers**. Left dormant
   deliberately today (a pre-09-06 bid may still rest); decide it once, do not
   let it drift.
9. **The decision map is exhausted** — 32 of 32 closed. Its third queue,
   *decided but never built*, has ~9 live items and belongs to nobody.

**Joe-gated:** whether to fund shard 0 so single markets work. (The exposure
ceiling question was asked and answered the same day — removed. Nothing else
is waiting on him.)

---

## 2026-09-07 (second session) — tonight's check had no instrument on the box and the wrong reading written down; attention was paying a live-game cadence for a line two days out

**STATE at close.** `main` = **`42e667f`**, pushed. **Live is deliberately
NOT on `main`, and that is the first thing to check before deploying.**

    live     763adad   read back from /api/health at 16:2xZ; recorder writing
    demo     cc8de80   NOT redeployed this session, and that is fine
    main     42e667f   five commits ahead of live, six ahead of demo

**Re-read 2026-09-07 16:26Z, next session:** live is still `763adad` off
`/api/health` `build.git_sha`, recorder writing (age 81s). `main` has moved on
to `9a2c1c0` (the demo-row fix, docs only) — **item 2 still ships `9e7e6c7` and
`ca248d7`; nothing deployable was added.** Live is now six commits behind main,
not five, and every one of the extra is documentation.

**Verify all three with `/api/health` `build.git_sha` rather than believing
this table** — the 09-06 entry said "deployed on `7ed20fd`" while live had been
on `4a6d63e` the whole time, and the partner then ranked a day's work around
it. **This table got the demo row wrong on its first writing today**, for the
same reason: it was written from "I deployed" rather than from a read. Only
live was deployed. Demo answers slowly on a cold start — an empty first `curl`
is the machine waking, not an outage; retry before concluding anything.

Demo is deliberately left behind: it carries no credentials and no execution
path, nothing tonight needs it, and deploying it now would ship ADR 0111 to a
second place and give this table a third sha to keep straight.

The five unshipped commits, and what each would put on the box:

| commit | what it is | ships? |
|---|---|---|
| `9e7e6c7` | **ADR 0111**, `backend/odds/timing.py` | **yes — the one being held** |
| `4524a56` | league→sport-key guard | no, tests only |
| `a76559d` | session record | no, docs only |
| `ca248d7` | `sweepTone` ordering + tests | **yes — frontend** |
| `42e667f` | the 03:37Z derivation | no, docs only |

ADR 0111 is held back **on purpose**: it changes `desk_wants`, which runs on
the same pass as tonight's one-shot NFL bootstrap. Holding it costs one evening
of a cadence Joe will not notice; shipping it costs the observation if it is
wrong. **Deploy after the bootstrap is confirmed, not before** — and note the
`sweepTone` change rides along in the same deploy, which is fine and is item 5.

Tree clean, no worktrees, no other lanes. Decision map still 0 open. Full
local suite **6307 passed / 10 xfailed** (9m31s); CI green on every push.

**The partner ran first**, on state read from `/api/health` and `gh` rather
than from the previous entry, and its ranking is what was executed. One thing
it got wrong is recorded in its own report: it nearly killed the Scout refusal
fixture on a belief that Scout has no caller. `backend/api/routers/scout.py:25`
imports `agents.scout_desk` and four seats spend real money through it.

### The finding that reordered the day: the check had no instrument

`NEXT.md`'s item 1 was *"read the `unmatched_items` collapse."* There was no
way to do that. No `unmatched_items` query in `inspect_live_db`'s whitelist, no
API route serving it, and `ls /app/scripts/` on the live box returns 14 files
with `list_unmatched.py` not among them. The pre-flight's own 07:21Z number was
taken as **ad-hoc SQL over `flyctl ssh`** — the thing `inspect_live_db.py`'s
ruling forbids in those words, *"nothing that carries its own source in the
command line."*

Shipped (`5275d1c`). The script now declares `/app/scripts/list_unmatched.py`,
which makes `TestTheSshInvokedScriptsSurviveDockerignore` **demand** the
`!scripts/list_unmatched.py` line rather than leave it to be remembered — that
allowlist has failed five times and this is the first addition where the two
halves cannot be separated. `--league` added: exact, case-sensitive, a bound
parameter, with the cut echoed in every count line including the empty one.

### And the reading written down would have called tonight's success a failure

This is the more important half. The plan said *"after the first sweep expect
32 → ~16, then 16 → ~0."* **The count will not fall.** Nothing sets
`unmatched_items.resolved` and nothing deletes on a link — `linker.py` only
upserts — so a row that stops failing goes **stale in place** until
`retention.DEFAULT_UNMATCHED_RETENTION_MS` prunes it **seven days** later on
`last_seen_ms`.

So **32 rows at 04:00Z is the success case.** The broken-link case is 32 rows
all carrying a *fresh* stamp. Corrected in the measurement doc (a CORRECTION
section) and in item 1 below.

### The instrument needed one fix before it was usable, found by running it

Its first live run returned **75.8 KB for 66 rows** — lines of 1,300 to 2,249
characters. `KXNFLTEAMTOTAL`'s `detail` is the whole points ladder joined by
" vs ", ~2,100 characters, and a column table takes its width from its worst
cell. The `last_seen` column — the *only* column tonight's reading uses — was
two thousand characters right of where anyone looks. Cells are now cut at 80
with the count of cuts printed and `--full` to recover them. Same read: **17 KB**,
52 cells cut. `763adad`, deployed and verified.

### THE BASELINE FOR TONIGHT, re-taken through the shipped instrument at 15:30Z

| series | rows | reason | `last_seen` |
|---|---|---|---|
| `KXNFLGAME` | **32** | no sportsbook fixture within the commence-time window | 2026-09-07 15:30 |
| `KXNFLSPREAD` | **16** | no linked game event for fixture … | 2026-09-07 15:30 |
| `KXNFLTOTAL` | 16 | expected 2 sides, got … | 2026-09-07 15:30 |
| `KXNFLTEAMTOTAL` | 2 | expected 2 sides, got … | 2026-09-07 15:30 |
| | **66** | | **0 stale** |

**All 66 carry the same fresh stamp**, which is what makes tonight legible:
nothing is frozen now, so anything frozen at 04:00Z is something the sweep
fixed. The total is 66 and not the 60 recorded at 07:21Z — **the growth is
entirely in the ladder class** (12 → 18), and the two classes tonight is about
are unchanged. Do not read the total as drift.

### ADR 0111 — attention was paying a live-game cadence for a line 45 hours out

`desk_wants`' attended branch had **no horizon at all**. The floor branch one
line below had always checked `soonest - now_ms > floor_horizon_ms` and
skipped; the attended branch gave every sport inside the caller's 48-hour
window the ten-minute cadence. 24 credits/hour/sport against a 300-credit
slice: 2 sports = 6.25 attended hours, **3 sports = 4.17**, 4 = 3.13. Measured
dwell runs 2.6–324 minutes a day and 20260827 spent the whole slice in **4.88
hours** — so the third sport alone takes the attended budget below a day Joe
has already had, and the third sport arrives tonight with its kickoff ~45 h
away.

Now **tiered, not cut**: ten minutes inside twelve hours, the floor's hourly
rate beyond it, never dropped. The cut was rejected because
`test_attention_overrides_the_horizon` records the standing rule that a far
fixture someone is looking at gets priced — Joe bets Sunday's NFL on Friday,
and cutting would take the desk dark on exactly those rows past the staleness
gate. **No published credit figure moves**; what changes is how fast the slice
is consumed inside its own cap.

The partner's better alternative was checked and **is not available**:
`attention.normalise_path` splits on `?` before storing, so `desk_attention`
records `/board`, never `/board?league=…`. The record carries which *screen*,
never which *league*. ADR 0111 records it as the next lever.

### The link between Kalshi and the odds feed had no test on either side

`IN_SCOPE_LEAGUES` turns `"Pro Football"` into the URL segment in
`/v4/sports/americanfootball_nfl/odds`, and nothing asserted it. The only
`sport_key ==` assertion in `test_discovery.py` was MLB's. A typo does not
raise — the vendor 404s and the sport never gets fixtures, which reads exactly
like a sport being out of season. Five tests now, and three mutants that were
all green this morning are red.

### Killed / not taken, so nobody re-derives them

- **Capturing an NFL odds wire fixture before tonight.** No NFL odds payload
  has ever been parsed by any test — the only captured Odds API response is
  MLB. Deliberately not pre-empted: tonight is a 4-credit test with a 30-minute
  backoff on failure, which is cheaper than any capture, and a capture run from
  the laptop spends a credit `api_credits` never records, putting the ledger
  out by 4 in silence. **Capture AFTER it succeeds**, and write the ledger
  drift into the measurement doc rather than leaving it silent.
- **Watching the credit ledger tonight.** Tonight is one 4-credit call against
  a ~366-credit day. Invisible. Sunday 09-13 is the day that matters.

### Still open, in order

1. ~~**Tonight, from ~03:35Z 09-08: confirm the first NFL sweep fired**~~
   **DONE 2026-09-08 03:41Z. IT FIRED AND BOTH CLASSES LINKED.**

   `api_credits` carries one `/sports/americanfootball_nfl/odds` row at
   **03:23:58.664Z**, cost 4, `trigger` NULL — a bootstrap, 3.9 minutes after
   the 03:20Z horizon crossing and inside the ~03:37Z bound. It is the newest
   `served` row in `odds_sweep_log`, with the expected props `skipped` row on
   the same pass.

   **Read on `last_seen`, and the count did not move — 66 rows, as designed.**

   | series | frozen @ 03:05 | fresh @ 03:39 | reading |
   |---|---|---|---|
   | `KXNFLGAME` | **32** | 0 | **linked** |
   | `KXNFLSPREAD` | **16** | 0 | **linked** |
   | `KXNFLTOTAL` | 0 | 16 | still failing, by scope |
   | `KXNFLTEAMTOTAL` | 0 | 2 | same |

   03:05 is the last pass before the sweep. The partition is exact — every row
   predicted to link is frozen, every row predicted to keep failing is fresh,
   and none falls on the wrong side. Budget day 20260907 closed at **300 of
   700** across 75 calls.

   **The two 09-07 baselines are what make this readable.** One baseline could
   not have separated "the sweep fixed 48 rows" from "the queue stops stamping
   at night"; the 16:25Z re-read established it re-stamps every pass. Full
   result and its four *does-not-establish* caveats:
   `docs/measurements/2026-09-07-nfl-live-path-preflight.md`.

   **The 48 frozen rows are stale, not resolved.** They disappear seven days
   after 03:05Z. Anyone returning to this queue mid-week must read the stamp,
   not the count — the same trap this item was rewritten to avoid.
2. ~~**Deploy ADR 0111** (`9e7e6c7`)~~ **DONE 2026-09-08 03:43Z**, immediately
   after item 1 confirmed, carrying `ca248d7` (`sweepTone`) in the same deploy
   as planned. **The command in the previous entry was wrong and would not
   run**: the workflow's inputs are `instance` and `confirm_live`, not
   `target`. `gh workflow run deploy.yml -f target=live` returns HTTP 422. The
   working form, and the one to write down:

       gh workflow run deploy.yml -f instance=live -f confirm_live=kalshi-cockpit

   `confirm_live` is a **typed** app name rather than a checkbox, deliberately
   (`.github/workflows/deploy.yml:13-15`) — a dropdown mis-tap on a phone is a
   plausible way to deploy the money instance by accident. Do not paper over
   that by scripting it away.
3. ~~**Capture the NFL odds wire fixture**~~ **DONE 2026-09-08 04:09Z.**
   `scripts/capture_nfl_odds_fixture.py --confirm-spend-4` →
   `tests/fixtures/odds_nfl_h2h_spreads.json` (926 KB): **272 events** — the
   whole regular season in one response — 30 books, markets `h2h`/`h2h_lay`/
   `spreads`, handicaps −14.5 to +14.5 over 2,278 outcomes, all half-integer.
   Ten tests in `tests/test_odds.py`.

   **LEDGER DRIFT: +4 credits `api_credits` will never show.** The table is
   written by the runner on the box; this call went laptop→vendor. Every
   `credits-day`/`credits-month` read for 2026-09-08 is 4 low. Reconciling
   figures are the vendor headers: `x-requests-remaining 17584`,
   `x-requests-used 2416`.

   **The shape is live's, not the laptop's, and it nearly went the other way.**
   `fly.live.toml` sets `ODDS_MARKETS = "h2h,spreads"`; local `.env` has
   `ODDS_MARKETS=h2h`. Reading the environment would have bought a **two**-credit
   payload of a request the recorder never makes and pinned a code path nobody
   runs, while looking correct. Pinned constant + cost guard now.

   **Two tests could not have been written against the MLB capture**: football
   handicaps are a wide half-point range where baseball's run line is a fixed
   ±1.5; and `TestTheDeployedRequestBuysNoFootballTotals` is the *evidence* for
   the "scope, not a defect" reading of tonight's 16 re-stamping `KXNFLTOTAL`
   rows. It fails if `ODDS_MARKETS` ever gains `totals` — correct, because at
   that moment those rows become linkable and the per-sweep cost rises by
   `len(regions)`.

   **One mutation stayed green and the reason is worth carrying.** Disabling
   `if market_key in EXCLUDED_MARKETS:` changed nothing, because that line only
   picks the log message — the real gate is the `PRICEABLE_MARKETS` whitelist
   at `client.py:567`. Aiming at that (M4) turns both lay tests red, the MLB
   one included. **A green mutation has two readings — decoration, or a missed
   guard — and only reading the code separates them.**
4. ~~**The Sunday 09-13 convergence.**~~ **TAKEN 2026-09-08, zero credits.**
   `docs/measurements/2026-09-08-nfl-sunday-credit-convergence.md`.

   **The convergence is real and cheap: the 00:20Z nighter's cluster costs 28
   credits of 700, ~4%.** NFL's whole scheduled demand for 09-13 is **124**
   (3 clusters, 21 window + 10 floor calls) — which **reproduces** the 124
   already published on 2026-09-06 rather than replacing it. Against every
   observed non-NFL day (180–496), `base + 124` lands 304–620. **Scheduled
   demand alone does not bind.**

   **What can bind is an attended Sunday, and the sub-caps are not budgeted to
   fit:** scheduled base 304 + NFL 124 + attention slice 300 + tap reserve 150
   = **878 against a 700 cap**, drawn first-come-first-served with **no
   reservation between spenders** (`budget.py:218` is a flat
   `remaining_today < cost`). **The day cap is load-bearing, not slack** — and
   that half is a code fact, independent of every projection.

   **Do not repeat the two errors this took.** (1) The first figure was **116**,
   from restating `SweepSlot.is_due` as `fire_from <= now < fire_until` when
   production's is `<=` on both ends — the strict `<` drops the seventh call of
   every window. The script printed `7 calls per full window` eight lines above
   a body producing six. **A consumer that restates a predicate is not covered
   by the test that pins the predicate**, and a new derivation disagreeing with
   a published number must halt rather than publish. (2) It planned once at day
   start where `decide_sweeps` replans every pass, hiding six 5-cluster days;
   the season worst is **~152–156**, not 140. `tests/test_simulate_nfl_sunday_
   credits.py` pins both, verified by mutation.

   **"Displacement makes the ceiling loose" is false and was believed here.**
   A displaced attention buy is *relabelled* NULL, not removed, and leaves the
   slice unspent to fund a later hour — so under the premise that matters
   (slice exhausted) it saves **zero**. General form: a mechanism that relabels
   spend is not a saving.

   **Binding is two states, not one.** Partial refusal comes first — slots
   reserve their tails and the floor loop runs **alphabetically**
   (`timing.py:2322`), so NCAAF/NFL are served before MLB and **WNBA dies
   first**; the slate degrades. The full stop (`fire=()`, everything silent to
   10:00Z) needs `remaining == 0` and the earlier refusals are what prevent
   reaching it.

   **The base is NOT a Sunday base and the prior doc's limitation is NOT
   retired** — an earlier draft of this item claimed both. 2026-09-07 is Labor
   Day, so 20260906/07 are the only NCAAF Sunday+Monday slate of the year; the
   Sunday-with-NFL cell is still **n = 0**; and six of the seven base days
   predate ADR 0111. Worse, the comfortable central estimate used a Sunday with
   32 attention credits — an *unattended* day — to project the day Joe is most
   likely to watch all afternoon.

   **Still open, and it is now the only live term:** whether the slice actually
   gets spent on 09-13. After 10:00Z on 09-14 run `credits-day --date 20260913`,
   `sweep-log` and `visit-freshness`, and split the mechanisms off
   `odds_sweep_log.detail` rather than `api_credits.trigger`, which pools them
   and is displaceable.
5. ~~**The calm strip after a mid-day cap**~~ **DONE this session, and the
   diagnosis in the previous entry was not quite the defect.** `sweepTone` did
   have a `refused` branch; it could not be *reached* on the day it mattered.
   Sweeps run from 10:00Z, the cap binds at 15:40Z, and `last_sweep_ms` is
   still inside the budget day — so "the day's sweeps have run" matched first
   and returned `calm` over a recorder stopped until tomorrow. The refusal test
   now runs **above** it. The rule: **the tone describes the most recent look,
   not the best thing that happened today.** Ships in the same deploy as ADR
   0111 (item 2), not before.
6. **`window_status` cannot predict a bootstrap** (lane B residual 1) —
   demoted, and the reason is sized: 28 call sites, a new DB reader and two
   guard rewrites. The screen-facing half is folded into item 5.
7. **The `eu` lever, 2026-09-28** — ADR 0110's measurements first.
8. **`parlay_positions` on 2026-09-15**; **`cryptography` bump ~=49.0 on
   2026-09-15**, gate `tests/test_rest.py::TestSigningContract` etc.
9. **Scout Anthropic refusal fixture (ADR 0106 §5.2)** — one billed call. NOT
   dead code: `backend/api/routers/scout.py:25` imports `agents.scout_desk`
   and four seats spend real money through it.
10. **`combo_orders` reconciliation** — answer *who reads this table* first.
    If nobody, either delete the write path or wire a filled combo into
    `/hedge`, which is the only reason it should exist given combos are
    enter-only in 40 of 40 books. Do not build the loop as previously scoped.

**Joe-gated: nothing.**

---

## 2026-09-07 (earlier session) — the NFL path is pre-flighted and its first sweep is due tonight by construction; a failed look and a spent day get their own words; the watcher stops asking the venue about a bid that filled

**STATE at close.** `main` = the sha in `git log -1`, pushed, CI on it is
the thing to read (`gh run list --limit 3`). **Live and demo: read
`/api/health` `build.git_sha` on both** before believing anything about them;
this entry says what was dispatched, not what is running. Tree clean, four
lane branches merged and deleted, no worktrees. Decision map still 0 open.

**The partner ran first on verified state** (sha read from `/api/health`,
not from the previous entry — its lesson) and returned a ranking that
overturned two of the last entry's items and killed one. Everything below is
that ranking executed, four lanes: A here, B/D/E in worktrees, disjoint files.

### Lane A — eight zero-credit checks on the NFL path, and the one that is empty is empty on schedule

`docs/measurements/2026-09-07-nfl-live-path-preflight.md`. The feed lists
`americanfootball_nfl` active (17,896 of 20,000 credits left this month);
discovery holds **50 open NFL events** for the next nine days (16 `KXNFLGAME`,
16 `KXNFLSPREAD`, 16 `KXNFLTOTAL`, 2 `KXNFLTEAMTOTAL`) under exactly
`Pro Football`; `/api/slate?league=americanfootball_nfl` echoes the filter
with an honest empty set. **`odds_snapshots` has 0 NFL fixtures and
`api_credits` 0 NFL rows, lifetime — and that is correct today.** Replaying
`decide_sweeps` read-only on the live DB with the runner's inputs
reconstructed: NFL's soonest Kalshi event is **67 h out against the 48 h
bootstrap horizon**. It crosses at **2026-09-08 03:20Z** and the next full
pass (every 15 min, `allow_bootstrap=True` by default on the ingest path)
buys it. Nothing else gates it — no failed sweep to back off from, and the
attention slice does not apply to `BOOTSTRAP`.

**The 4-credit early buy the plan allowed was not available.** The tap route
refuses a sport with no stored fixture (`routers/odds.py:159-173`), so the
desk's own spend path cannot bootstrap a new sport, and no side channel was
used. **Do not read "0 NFL fixtures" as a failure before 03:35Z 09-08.**

**The Wednesday baseline, by reason** (`unmatched_items`, `resolved = 0`,
`league = 'Pro Football'`, 07:21Z): `no sportsbook fixture within the
commence-time window` **32** rows (all 32 `KXNFLGAME`, Weeks 1 and 2);
`no linked game event for fixture …` **16** (`KXNFLSPREAD`, links through its
game); `expected 2 sides, got 19/27/28` **12** (`KXNFLTOTAL`/`TEAMTOTAL`
ladders — **scope, not a defect**, the feed buys no totals). Do not read
`event_links`.

**The sentence that stood here — "after the first sweep expect 32 → ~16, then
16 → ~0" — was WRONG and is corrected below.** It would have read tonight's
success as a failure. See the CORRECTION section in the measurement doc.

### Lane B — `failed` and the daily cap were both wearing the quiet's words

`WindowBanner.tsx` tested `refused` by name and let every other outcome fall
to *"looks identical to a quiet market from here"* — so an Odds API 401/429
on Wednesday would have rendered as a quiet market with the truth in the small
print. And `runner.py` recorded the `remaining == 0` stop as `SKIPPED` while
`sweeplog.py:78` defines `REFUSED` as "the budget declined — *we* stopped".
Now: `SweepDecision.refused_by_budget` (True only on that return) → the
runner writes `REFUSED`; the banner has a `failed` branch by name. **The
`next_call_ms` agreement test failed on the original code** — at zero credits
the loop returned `fire=()` while the payload said "now" — fixed in
`window_status`. Six mutations, all red. `tests/test_inspect_live_db.py`'s
exhausted-day fixture now describes the new shape (41 refused / 3 skipped).

*Two residuals, recorded:* (1) `window_status` takes no `in_scope`, so on the
pass the loop bootstraps a fixture-less sport the screen says nothing is
coming — **that is tonight's NFL sweep**, and the loop buys regardless; small,
Monday/Tuesday. (2) On a day where sweeps ran and *then* the cap bound,
`sweptThisDay` is true and the strip is calm with "the day's sweeps have
run"; only the detail line names the stop. Not a lie; not loud either.

### Lane D — a venue 404 on a combo cancel is an answer, and the watcher had been asking once a minute for six days

Gate passed on the live DB: `combo_orders` row 2 (the 09-01 bid that FILLED
at 21:40Z and settled) was still `resting`, and `bid_watch` logged `ERROR …
left working and will be retried on the next pass` at 07:20, 07:21, 07:22Z —
every minute since 2026-09-01 22:41Z, ~7,700 times. Now
`STATUS_GONE_AT_VENUE = "gone_at_venue"` is terminal (not `cancelled`: money
moved); the watcher and the cancel route split `KalshiAPIError` 404 from
everything else — 404 marks the row and logs once at warning, anything else
keeps the retry. The three "still working" queries build `NOT IN` from
`TERMINAL_STATUSES` instead of four hand-typed placeholders. No schema change
(`status` has no CHECK). Six mutations red. **After deploy, the per-minute
ERROR line should stop within one minute — check `flyctl logs`.**
`combo-bids-tail` and `analyse_bet_presence.py` will show the new status as
unfamiliar text; neither drops the row.

### Lane E — ADR 0110, and dropping `eu` empties the sharp anchor

`docs/adr/0110-the-eu-region-is-the-only-feed-lever-left.md` records the
props kill, the totals refusal (6 credits a call; 496 × 1.5 > 700), the
`us`-only lever dated 2026-09-28 with its two preconditions, the five
`sorted(fixtures)` reasons with their 09-13/09-20 gate and the named non-fix
(a per-sport reservation, never a sort key), and the `exchange_index` kill.
**New in it:** `SHARP_BOOKS` (`runner.py:152`) is `{pinnacle, betfair_ex_eu,
betfair_ex_uk, matchbook}` — none is a `us` book — so `h2h,spreads,totals ×
us` trades every sharp-anchored fair value (73.0% of the pinned record) for a
soft consensus. The ADR lists what to measure first, including whether `uk`
at cost 3 keeps Pinnacle. Nothing in `fly.live.toml` moved.

### Killed this session, so nobody re-derives them

- **`exchange_index` on the manual order path** — the create body carries no
  shard on either path; `combo_bids` is right *around* the create (shard-scoped
  balance, shard persisted for the cancel). Real gap on an armed route with 0
  of 27 real bets, all NFL on shard 0, baseball leaving 09-27. ADR 0110.
- **`sorted(fixtures)` reordering** — five reasons, ADR 0110; gated.
- **The 4-credit early NFL buy** — not possible through the tap; not needed.

### Still open, in order

1. **Tonight, from ~03:35Z 09-08: confirm the first NFL sweep fired**, and
   read it the way the two corrections below say, not the way this item said
   this morning.
   - `sweep-log` should show a **`served`** row, `sport_key =
     americanfootball_nfl`, detail beginning `americanfootball_nfl has no
     stored sportsbook fixtures`. A `skipped` props row lands right behind it
     and is expected, not a fault. **Do not grep `api_credits` for the string
     `bootstrap`** — `trigger` is NULL on a bootstrap; only MANUAL and
     ATTENTION are stamped.
   - **03:35Z is not a deadline.** `window_status` cannot see a sport with no
     stored fixture, so its null `next_call_ms` feeds `Tempo.next_wake_ms`
     (`scripts/run_loop.py:1121`) and the loop may pace itself slowly for the
     buy it is about to make. A bootstrap at 04:10Z is the design working.
   - **Read `last_seen`, never the count** — corrected 15:20Z, and the old
     reading would have called a success a failure. Nothing sets
     `unmatched_items.resolved` and nothing deletes on a link, so a fixed row
     goes *stale in place* for the 7 days of
     `retention.DEFAULT_UNMATCHED_RETENTION_MS`. **`Pro Football` still
     holding 32 rows at 04:00Z is the SUCCESS case**; the broken-link case is
     32 rows all carrying a *fresh* stamp. Full table in
     `docs/measurements/2026-09-07-nfl-live-path-preflight.md` §CORRECTION.
   - The instrument is shipped as of this session and ordered by
     `last_seen_ms DESC` so the live rows sort on top:

         flyctl ssh console -a kalshi-cockpit -C "python /app/scripts/list_unmatched.py --db /data/cockpit.db --league 'Pro Football'"

   - **Do not watch the credit ledger.** Tonight is one 4-credit call against
     a ~366-credit day; 4 credits is invisible. The day that matters is
     Sunday 09-13 — see item 2.
2. **`window_status` cannot predict a bootstrap** (lane B residual 1). Pass
   `in_scope` through and mirror the candidate filter; one test driving both
   at a fixture-less sport inside the horizon.
3. **The `eu` lever, 2026-09-28** — ADR 0110's measurements first.
4. **`parlay_positions` on 2026-09-15**; **`cryptography` bump ~=49.0 on
   2026-09-15**, gate `tests/test_rest.py::TestSigningContract` etc.
5. **Scout Anthropic refusal fixture (ADR 0106 §5.2)** — one billed call.
6. **`combo_orders` reconciliation loop** — still nothing updates a row on
   fill or settlement; lane D closed only the 404 half. No screen reads it.
7. The lane B residual 2 (calm strip after a mid-day cap) — words only.

**Joe-gated: nothing.**

---

# The session index

Every session entry ever written to this file, newest date first. Full text in
the linked archive file, unchanged.

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
