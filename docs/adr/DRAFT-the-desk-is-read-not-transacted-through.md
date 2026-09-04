# ADR DRAFT — The desk is read, not transacted through

**Status:** Draft. Ordinal taken at merge, after `git fetch`
(`docs/adr/README.md`). Lane A, 2026-09-04.
**Date:** 2026-09-04.
**Decides:** an operational finding and the work it stops funding. It is
**not an amendment to ADR 0071** — that is a purpose ADR settled in Joe's own
answers, and nothing here re-opens a purpose question. The partner ruled
2026-09-04 that this is its own record (`tasks/NEXT.md`, 2026-09-04 entry,
"Still open" item 2).
**Sources:** `docs/measurements/2026-09-04-presence-at-the-moment-of-a-bet-result.md`
(the result) and `2026-09-03-presence-at-the-moment-of-a-bet-registration.md`
(the registration, §2.4 and §10); ADR 0063, 0065, 0073, 0094; decision-map
ticket #11 on `josephsapinoso/kalshi-cockpit`.
**Touches nothing decided by** ADR 0015 (the gate's floor), ADR 0018 (arming is
a code change), ADR 0038 (the hunt is closed), ADR 0078 (what the desk watches
that he already holds).

## 1. The census

Between `2026-08-25T16:03Z` and `2026-09-04T00:00Z` — the window of the
presence measurement, `W_start = MIN(seen_ms)` over `desk_attention` — Joe
placed **27 taker hand fills on Kalshi**, forming **12 sittings** (fills within
60 minutes) across **7 budget days** (result §2). Over the same window and for
the whole life of the table, `manual_orders` real rows = **0** (result §2, the
§2.4 exclusion; registration §2.4 records the same 0 at the 2026-09-02 census).
The path those rows would come from has been armed the entire time:
`MANUAL_ORDERS_ARE_DRY_RUNS = False` in `backend/store/manual_orders.py:94`,
shipped in `26a8d70` on 2026-08-26 on Joe's word (ADR 0073 §6 addendum; the
constant's own comment carries his sentence).

So: **0 of 27**. That is a census count, not a test — it needs no
registration, no null and no p-value, and it is the load-bearing number in this
document.

What the registered measurement itself found, said once and the only way it may
be said (result §1, §5): at **8 of 12** sittings a `desk_attention` visit was
open within ±5 minutes; the eight containing visits were 2.7 to 31.1 minutes
long, with the fill landing 1 to 9 minutes after the visit opened; a day-shifted
permutation puts the chance rate at 2.60 of 12 (`p_perm = 0.0004`, `k* = 7`).
**The registered verdict is UNRESOLVED — CONCENTRATION**: 5 of the 8 come from
two budget days and the finding does not survive dropping one of them. Under
registration §10 that verdict **funds nothing and kills nothing**, and this ADR
does not draw on it. The verdict describes *presence*. The decision below rests
on the census, which describes *use*.

The two are not in tension. Read together they say: the desk is often open
shortly before a Kalshi bet, and the bet is then placed somewhere else. That is
what "a read surface" means here.

## 2. Three entry designs for one datum

The datum is Joe's own pre-bet probability. The repo has built three ways for
him to type it into the desk.

1. **The calibration study's entry form** (ADR 0044, study opened
   2026-08-18). Joe stopped the study on 2026-08-20 (registration Amendment 2,
   stopped without result — ADR 0044 Amendment 3 and 4 both restate this). The
   form kept running for two days on a stopped study and was retired on
   2026-08-22 in `56a8dae`, which cut `frontend/src/app/estimate/page.tsx` to
   the read-only RECORD; the page's own header records why (ADR 0065 §2).
2. **ADR 0065's typed estimate on the manual ticket**, blind-first: P(YES) is
   the ticket's first field and the ask is masked until it is entered; the
   route refuses without `p_yes_bp`. Its yield is bounded above by the table it
   writes into — `manual_orders`, 0 real rows — so **zero hand bets have
   carried it**. ADR 0073 §4 also found the mask had never held on the one
   screen the ticket was first mounted on.
3. **#11's price-free log form** (ADR 0094, 2026-09-01). The backend shipped —
   the write path unblocked, the embargo rescoped, five `call_*` columns at
   SCHEMA_VERSION v32, a scorer against Kalshi's close, and a singular read.
   **The screen never shipped**: `frontend/src/lib/api.ts:2220`'s
   `logEstimate` has no caller outside `api.ts`, and no page names "log a
   call" (grep, this tree, 2026-09-04). ADR 0094 §9's own falsification clock
   — seven days from the screen shipping — therefore never started.

Their combined yield, as the record states it: **one typed estimate in
`bet_estimates`, ever**, dated 2026-08-22 (ADR 0094 §1's table, a live read
taken 2026-09-01; ticket #11's resolution carries the same figure). Two things
about that one row this lane could **not** verify and does not claim: which of
the three surfaces wrote it (the date is the day the study form retired and
the ticket landed, and `manual_orders` is empty, which points at the form, but
nothing read here says so), and whether the count is still 1 today — the live
database is not readable from a lane and the newest read is 2026-09-01.

Joe's reason is in the ticket. #11's resolving comment reads: *"Joe's reason,
asked directly: the Kalshi app is faster and he is already in it."* That is the
resolving session's report of his answer, not a sentence he typed, and it is
cited as such. ADR 0094 §1 and ADR 0065's 2026-09-01 amendment carry it in the
same words.

Three designs, one row, and a stated reason that none of the three addresses.
A fourth design would be a bet against that record.

## 3. The decision

**The desk is a read surface.** Work that assumes Joe will type into it or
transact through it is not funded on the current record.

Killed by the partner on 2026-09-04 (`tasks/NEXT.md`, "Killed by the partner,
stated plainly"), and recorded here so no session re-opens them as forgotten
rather than decided:

- **#11's price-free log form.** ADR 0094's backend stays as built; the digest
  link and the screen (its decisions 3, 4, 5, 9) are not built.
- **Wiring `/api/estimates/last-scored` to any screen.**
  `backend/api/routes.py:3820` serves a source that is structurally empty —
  `last_scored_call` selects `is_study_row = 0`, and no such row can exist
  without the form above — and has **zero frontend callers**
  (`grep last-scored|last_scored|lastScored frontend/src`: no matches). The
  route **stays**. It gets an honest docstring and an absence pin — the fifth
  instance of built-and-uncalled this repo has catalogued — as a separate
  build, not in this ADR, and pending Joe's question D.

The reason is the one ADR 0071 §2.1 already gives: Joe bets by hand whether or
not the desk exists, and the desk does not manufacture action. A form nobody
fills is not neutral — it is a screen claiming a habit that the record says is
not there, which is the same defect ADR 0094 §1 found in ticket #11's own
premise (*"It is stored on every row"*, when it was stored on one).

## 4. What this does not decide

- **ADR 0071 §2.2 is unchanged.** Price transparency at the moment of a bet
  stays the job. What the record narrows is the *venue* of that moment: a
  short read on the desk — 2.7 to 31.1 minutes, fill 1 to 9 minutes in, at the
  8 sittings where a visit was open — that ends in the Kalshi app. The job is
  to make that read worth taking; it is not to move the tap.
- **`manual_orders` is not retired.** Registration §10 says in its own words
  that the 0 rows *"were already known and are not this measurement's
  finding"*, and that even the strong verdict *"does not on its own authorise
  removing it"*. The path stays armed as ADR 0073 left it; disarming it is a
  one-line code change and Joe's act (ADR 0018's pattern).
- **"Presence is solved" and "the desk is at the moment of a bet" are not
  written here** and may not be quoted from here. The registered verdict on
  presence is UNRESOLVED, the registration is closed, and a successor needs a
  tie-break rule fixed in advance and roughly 25 sittings (result §6).
- **Nothing about his sportsbook bets.** The population is Kalshi taker hand
  fills; `fills` cannot see a sportsbook slip, which is why ADR 0078 exists.
- **The engine's gate is untouched.** `gate.py` never reads `manual_orders`
  (ADR 0063 §2) and nothing here changes what it counts.

## 5. What would overturn it

Either of two things, and nothing softer:

- **A `manual_orders` real row from Joe's own tap.** One is enough to reopen
  the question; it would not by itself refund the killed items.
- **Joe saying so.** Question D on the 2026-09-04 artifact asks him directly
  whether #11's log screen is killed or kept (`tasks/NEXT.md`, "FOR JOE").
  His answer governs this ADR; if he keeps the screen, §3's first kill is
  withdrawn and ADR 0094 §9's seven-day clock starts when it ships.

A rise in `desk_attention` rows is **not** evidence against this ADR: the
schema comment above `CREATE TABLE desk_attention` (`backend/store/schema.sql`,
corrected 2026-09-04) says the row count measures dwell, not use, and dwell on
a read surface is consistent with everything above.

## 6. Consequences for the open queue

- **The next instrument is *which screen* is open at a bet**, not whether one
  is. A `path` column on `desk_attention` — pending Joe's question E. The
  schema comment already clears the way: its "a column that is always the same
  value is a claim about a future that does not exist yet" reasoning is stated
  there to *not* reach a column that varies, such as the page path. Because
  stamps are cadence-emitted, that column is dwell-weighted per screen, and
  the comment should say so when the column lands.
- **`/api/estimates/last-scored`**: docstring and absence pin, separate build,
  after Joe's D.
- Sessions planning UI work read this before proposing any input, form,
  confirm or tap on the desk that presumes a bet will pass through it. The
  burden is the census, and the census is 0 of 27.
