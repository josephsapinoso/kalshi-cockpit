# 0162 — The spine stops carrying decaying transacted-path counts

Written by lane E (`lane/spine-stops-carrying-counts`) with no ordinal;
**0162 was taken at the merge commit after `git fetch`**, per
`docs/adr/README.md`. No schema change, no code change, no route change.

Date: 2026-09-16
Status: accepted
Scope: `CLAUDE.md` (the transacted-path paragraph in "What is armed and what
is not", the duplicate restatement and the `/hedge` locks paragraph in "What
it is for", and a light mark on the gate's lifetime actionable-game count),
`docs/measurements/2026-09-17-transacted-path-census.md` (new),
`tests/test_transacted_path_count_is_not_restated.py` (new guard).

---

## 1. The defect

CLAUDE.md's transacted-path paragraph stated a live row count — how many
`manual_orders` rows, how many filled, how many open `parlay_positions` —
and that count went stale and was corrected four times in nine days:

    "two"                          until 2026-09-10
    "four by 2026-09-09"           until 2026-09-14
    "7 rows / 6 filled / 4 positions"  until 2026-09-15 (found six orders stale)
    "13 / 12 / 10"                 until 2026-09-17 (found stale two days later:
                                    three orders and seven positions off)

Each correction was itself a fresh snapshot, not a fix, because the thing
being measured moves every time Joe places a hand bet — which is the tool
doing its job, not a bug. A document every session is told to read at the
start of session (CLAUDE.md's own preamble) cannot carry a number on that
clock and still be trusted. The most recent edit, made the same evening this
ADR was written, updated the count to 16/14/17 and — by the same argument —
guaranteed a fifth correction before anyone read it twice.

The same shape existed twice more in the file once looked for: the `/hedge`
"zero locks in its life" paragraph restated a `position_state`/`derisk`/dead
breakdown dated 2026-09-15 that was *already* stale relative to this file's
own later transacted-path reading by the time both sentences sat in the same
document, and the E2/stake-basis paragraph in "What it is for" restated the
transacted-path population a second time under a different label ("The
population is now **16 real rows...**"), so a single stale count required
two separate corrections to fix.

## 2. The decision

**CLAUDE.md stops stating a live count of the transacted path.** In its
place it states the durable claim — three quantities circulate and they are
not the same number, name the table — and the instrument each one is read
with: `manual_orders` via `inspect_live_db.py manual-orders-audit`, filled
orders as the `status = 'filled'` subset of that same read, open
`parlay_positions` via `/api/hedge` (which lists `status = 'open'` only, so a
closed row would not show). Any figure for these three is stale on sight —
because Joe keeps betting, which is the point of the tool — and the
paragraph says so instead of quoting one.

**A point-in-time reading is not banned, it is relocated.** The last live
read (2026-09-17 ~00:40Z: 16 `manual_orders` rows, 14 filled, 2 unfilled; 17
open `parlay_positions`, ids 1-17; orders 1-2 have no position; positions
11-15 are hand-recorded with NULL `combo_ticker` and `placed_ms`) is written
once, dated, in `docs/measurements/2026-09-17-transacted-path-census.md`,
which is allowed to go stale because nothing points a session at it as
ground truth the way CLAUDE.md's own preamble points at CLAUDE.md.

**What survives the edit, because it is not a decaying number:**

- The three-quantities distinction itself, and the instruction to name the
  table rather than a bare digit.
- The structural fact that the two tables do not correspond row for row, by
  design: `record_position` (`backend/hedge.py:350`) has two callers —
  `backend/api/routers/hedge.py:73`, where Joe hand-types a ticket for a bet
  placed elsewhere and both join columns default to `None`, and
  `backend/api/routes.py:4612` on the order path, which always sets them.
  Verified by reading both call sites, not taken on the brief's word: line
  73 constructs `HeldPositionRequest` fields `combo_ticker` and `placed_ms`
  as optional, unset by Joe on a hand-recorded slip; line 4612 passes
  `combo_ticker=ticker, placed_ms=placed_ms` from the order it just placed.
  So an order can exist with no position and a position can exist with no
  order, and a `kalshi_combo` position with a NULL `combo_ticker` is a
  **designed state** ADR 0160's read correctly refuses to join
  (`no_order_row`), not a bookkeeping gap.
- The correction trail — described, not reproduced verbatim as a table, per
  `tasks/lessons.md` 2026-09-16 (tenth): quoting the *pattern* ("four
  corrections in nine days, the last one found stale two days after it was
  written") does not re-create the specific live-count shape a guard could
  re-trigger on; reproducing the exact table format would.

## 3. What else this ADR touches, and why

Grepping CLAUDE.md for every other figure that reads as a point-in-time
measurement rather than a settled constant, with the keep/move/mark call for
each:

| figure | call | reason |
|---|---|---|
| Transacted-path row counts (main target) | **moved** | see above |
| `/hedge`'s "zero locks" paragraph's `position_state`/`derisk`/dead counts | **moved** (counts dropped, instrument + re-check instruction kept) | already stale relative to this file's own later transacted-path reading; same decay shape |
| E2/stake-basis paragraph's restated "16 real rows, 14 filled, 2 unfilled" | **moved** (pointer to the transacted-path paragraph instead of a second restatement) | duplicating the count doubled the correction burden every time it changed |
| Gate's "the record has 2 in its whole life, both soft-book fallbacks" | **marked** | a cumulative live count of the same shape (the Gate screen's game count), but not this ADR's target; annotated with a pointer to re-derive it and a note that it decays the same way, left as a live count because re-deriving it correctly needs a live read this ADR's author did not have reason to take |
| `beta` fits (2026-08-16, 2026-08-25, `G` values) | **kept** | a formal, registered, spent measurement under a stopping rule that "is not coming" — settled, not decaying |
| Actionable-population re-audit ("51 rows across 15 games", 2026-09-01) | **kept as exemplar** | already dated and cites its instrument and its measurement doc; this is the pattern §2 generalises, not a defect |
| Credit-budget table (idle floor, attention cap, kickoff ceiling) | **kept** | policy constants derived from named config (`ODDS_ATTENTION_DAILY_CREDITS`, `ODDS_DAILY_CREDIT_BUDGET = 700`, `3` credits/call per ADR 0155), not a live row count; already self-caveated to "re-derive... the day the book list or the market list moves" |
| Cost-bar percentages, `TAKER_COEFFICIENT` | **kept** | measured constants / applied config, not a count that moves on its own |
| "67% of September's spend" | **kept** | scoped to a named, closed month — a historical fact, not an ongoing count |
| Combo book-depth claims ("40 of 40", "33 of 40") | **kept** | pinned by `tests/test_combo_book_depth_claims.py` against captured fixtures, not a live DB read |
| `manual_orders` census dated 2026-09-15 (registered, spent) | **kept** | the census is explicitly spent (§2 of its result doc); its scope (which six orders it covers) is a historical fact about *that* look, not an ongoing count — reworded in the E2 paragraph to say "any order placed after 2026-09-15 is outside it" instead of counting how many such orders exist today |
| "the ten open rows keep their stored number" (ADR 0160's no-backfill decision) | **kept** | describes the scope of a specific dated decision at the time it was made, not an ongoing count |

The distinction drawn throughout: a figure decays because the world moves
(Joe places another bet, another position opens) versus a figure is settled
by a measurement that is spent (a registered look that will not be re-run,
or a config-derived constant). Only the first kind moved or was marked.

## 4. Guard

**A narrow guard exists and is load-bearing; a broad one would not be.**

A generic digit-grep over CLAUDE.md would fire on ADR numbers, dates, line
numbers, the `beta` fits and the 300-game floor — exactly the noise the
brief for this work warned against, and exactly the "decoration" this
project's Testing section refuses.

What is testable, and different from that: **the paragraph must keep naming
its instruments, and none of the three concrete formats this number has
already broken in should recur.** Those three formats each were,
individually, wrong within days of being written —

    manual_orders     N rows, dry_run = ...
    N OPEN rows, ids 1-N
    **N real rows, N filled, N unfilled**

— so a regression to any one of them is the *same* failure returning, not a
new one to relitigate. `tests/test_transacted_path_count_is_not_restated.py`
pins:

1. The paragraph still names `manual-orders-audit`, `/api/hedge`, and the
   phrase "stale on sight" (matched at the token level, `\s+` between words,
   because CLAUDE.md is hard-wrapped and a phrase can fall across a line
   break — `tasks/lessons.md` 2026-09-16 twelfth and tenth entries, both hit
   while writing this guard; see §5).
2. None of the three killed shapes above appears anywhere in the file.

**Mutations run, each observed RED then restored to a byte-identical file**
(md5 `cfc4f51f7a54b17351eefc6a404f75cf` before, during-mutation-then-restore,
and after every one of the four runs below):

- Reinserted `manual_orders     16 rows, dry_run = 0` → RED
  (`test_none_of_the_killed_live_count_shapes_have_returned`).
- Reinserted `17 OPEN rows, ids 1-17` → RED (same test).
- Reinserted `**16 real rows, 14 filled, 2 unfilled**` → RED (same test).
- Renamed the sole occurrence of `manual-orders-audit` → RED
  (`test_it_still_names_every_instrument_and_the_disclaimer`).

All four restores were verified by re-hashing the file after undoing the
mutation with the same literal-replace script that inserted it, never with
`git checkout` (`tasks/lessons.md`, mutation-testing hazards).

**What this guard does not do.** It cannot stop a differently-worded live
count from being written — a fourth shape would need a fourth pattern added
to `_KILLED_SHAPES`, the day it happens, the same way
`test_a_question_for_joe_has_a_ticket.py` extends its wordings. It is a pin
on the three shapes that actually recurred, not a general ban on numbers.

## 5. What went wrong while writing this, corrected in the same session

The guard's first draft checked for the literal substring `"stale on
sight"` and failed RED against the very file it was meant to certify GREEN,
because the phrase fell across a hard line wrap in CLAUDE.md ("...stale on
sight\n..." became "...stale on\n  sight..." after word-wrapping the edit).
Matching at the token level (`re.compile(r"stale\s+on\s+sight")`) fixed it.
This is the same class of failure `tasks/lessons.md` 2026-09-16 (tenth)
names for a different guard on a different file; it recurred here on a fresh
one, which is itself worth recording rather than treating as resolved by
having a lesson about it.

## 6. What this does not decide

- Whether the gate's "2 in its whole life" figure should also move to a
  dated measurement doc. It is the same shape and is marked as such, but
  re-deriving a current number for it needs a live read this session did not
  have a reason to take under this ticket's scope; a successor may finish
  the job.
- Anything about the transacted path's actual current count. Read
  `docs/measurements/2026-09-17-transacted-path-census.md` for the last one
  taken, or re-run the instruments — never this ADR.
- Whether `/hedge` has produced a lock since 2026-09-15. That paragraph now
  says to re-check rather than stating a number; nobody has re-checked it
  under this ADR.
