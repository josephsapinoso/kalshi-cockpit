# Archive - `tasks/NEXT.md` session entries, second split of 2026-09-08

**Verbatim.** These entries were moved out of `tasks/NEXT.md` unchanged,
byte for byte, when that file stood at 90,706 bytes - 34.6% of the
262,144-byte ceiling. Nothing was summarised, reworded or dropped.

**Taken for readability, not for size.** The three entries here were the
closed narrative of 2026-09-07 and the first 2026-09-08 session; each
carried a `Still open` list superseded by the entry that stayed. Two
splits on one date, so this file carries `-second` rather than sharing the
name of `next-2026-09-08.md`, which stays byte for byte as it was.

The moved block hashes `md5 = e8c041c54a1b0d17bb8b54908c8204d7`.

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

