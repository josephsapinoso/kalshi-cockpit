# Desk route latency on a warm box, and why it does not retire the ANALYZE park

**Date:** 2026-09-16
**Instruments:** `scripts/time_live_routes.py` (3 reps); an unversioned curl
loop for the league chips (2 reps); `inspect_live_db.py read-incidents -n 20`
**Cost:** zero odds credits. Every call a `GET`; the only writer to
`desk_attention` is `POST /api/desk/attention`, which none of this touches.
**Live sha at read:** `5f4d1de`, machine `01M2NVZ4J319AM9TVR8YQK3SF4`.

**This document was rewritten after a measurement-skeptic audit.** Its first
draft concluded that the park at `tasks/NEXT.md:341` should be deleted because
no desk route approaches the 25 s read budget. That conclusion was wrong, in
the flattering direction, for the reason in §D. The superseded claim is stated
there rather than quietly dropped.

## What this establishes

That on a **warm** box on a Wednesday, thirteen desk routes and three league
chips all returned 200, with medians between 75 ms and 1,727 ms — between 0.3%
and 6.9% of the 25,000 ms budget **at the median**.

## What it does NOT establish

- **Nothing about the tail, which is the only thing the budget cares about.**
  The budget fires on the slowest request, not the median one. With 3 reps per
  route, 0 trips in 39 draws bounds the per-request trip rate no tighter than
  **7.7%** (rule of three); section B's 0 in 6 bounds it at **50%**. Per-rep
  maxima were not recorded and cannot be recovered — `time_live_routes.py:76`
  keeps only median and min.
- **Nothing about a cold or cache-evicted box**, which is the regime where the
  budget has actually fired. See §D.
- **Nothing about a full NCAAF slate.** Read on a Wednesday; NCAAF is
  Saturday 19.
- **Nothing about concurrency.** Sequential by design, so as not to load the
  box. Two phones and the recorder at once is a different question.
- **The page figures are measured in the most favourable possible order.**
  `time_live_routes.py:59` iterates `APIS + PAGES`, so `/api/parlays` warms the
  parlay read path immediately before `/parlays` is timed. Those are not
  first-tap costs.

*Harness gap, recorded:* `scripts/time_live_routes.py:1-6` has no "what this
does not establish" section, which CLAUDE.md requires of every measurement
harness. Section B's harness is a hand-written curl loop that exists nowhere in
the repo, so the one section covering the route class that has actually failed
in production is the one nobody can re-run. Both are worth fixing in whichever
change next touches that script; neither is fixed here.

## Section A — thirteen routes, 3 reps each, median of 3

    route                                  median      bytes
    ------------------------------------  --------  ---------
    /parlays                    (page)     1,727ms    518,837
    /hedge                      (page)     1,543ms    107,407
    /slate                      (page)     1,475ms  1,485,825
    /picks                      (page)     1,329ms     61,507
    /board                      (page)     1,227ms    409,932
    /api/parlays                           1,631ms     53,836   (min 628)
    /api/hedge                             1,540ms     29,921
    /api/window                              887ms      2,511
    /api/slate                               591ms    253,485
    /api/board?include_suppressed=false      368ms        615
    /api/odds/refreshable                    124ms      2,616
    /api/signal                              100ms      4,856
    /api/health                               75ms        711

All thirteen returned 200. The slowest **median** was 1,727 ms. This is a
statement about the centre, not the tail — and `/api/parlays` alone spread
628 ms to ≥1,631 ms across three consecutive warm reps, a factor of 2.6 inside
one run.

## Section B — the league chips, which section A does not cover

The route that tripped the budget is `/api/slate?league=<sport_key>`, and
`time_live_routes.py:37-46` carries no league-filtered entry. Timed by hand,
2 reps:

    /api/slate?league=americanfootball_nfl     1,380ms  1,183ms
    /api/slate?league=americanfootball_ncaaf   1,098ms  3,951ms
    /api/slate?league=baseball_mlb               729ms  1,048ms

**The NCAAF 3.6x spread is the most informative number here and it is not
explained.** 3,951 ms is the largest observation anywhere in this document —
larger than any section A median — on the exact route class with a six-incident
history, in the sport whose slate is Saturday's. The fixed plan is roughly
linear in window rows; if Saturday's window is "several times larger", these
premises extrapolate into **12–20 s**, i.e. into the budget's neighbourhood.
That arithmetic is offered as a reason to re-time on Saturday, not as a
prediction: n = 2 is too thin either to explain the spread or to dismiss it.

## Section C — the recorded incidents

`api_read_incidents` (whole-table per-kind section) holds **six** `read_budget`
rows, all within five minutes:

    2026-09-15T12:16:18Z .. 12:21:43Z   GET /api/slate?league=americanfootball_nfl
    elapsed 25,002 .. 25,014 ms         budget 25,000 ms
    OperationalError: interrupted

**That count is a FLOOR, and the censoring is correlated with the event.** The
instrument's own caveat (`inspect_live_db.py:409-410`) is that the writer is
best-effort under contention — so the incidents that go unrecorded are exactly
the ones under hard load, which is when the budget is likeliest to fire. Six is
not "six, give or take"; it is "six, biased low in the worst conditions". A
missing one looks like a user-visible "Backend unreachable" with no row and an
expired log line. *(The corroborating `health_probe` series was not read; it
should be, next time.)*

**These six are fixed.** `backend/api/routes.py:4640-4655` records the cause:
the league predicate was an `EXISTS` with `sport_key` in its `WHERE`, and
`sport_key` leads no index on `odds_event_id`, so for every window row whose
fixture was *not* in the requested league SQLite walked that league's whole
partition — once per row, in both statements, ~350 times per statement. MLB
looked fine because most rows match on the first probe. Now
`ORDER BY commence_ms LIMIT 1` against `idx_odds_event_commence`.

Verified rather than asserted: fix commit `2d8de82`, 2026-09-15 06:57:35-0700 =
**13:57Z**, i.e. 1h36m *after* the 12:16–12:21Z incidents, same UTC day;
`git merge-base --is-ancestor 2d8de82 5f4d1de` → yes, so it is in the live sha.
`tests/test_slate_league_cut_is_bounded.py` pins the plan for both leagues and
carries a working negative control (`:121-135`) asserting the *old* predicate
still produces the bad plan — which is the disabling-the-guard discipline
actually done, not claimed.

**Section B is consistent with the fix and inconsistent with nothing.** The old
predicate's cost is `O(non-matching window rows × league partition)`, so a
Wednesday window with few non-matching rows would be fast under the old code
too. The window row count was recorded for neither date, and that is the single
number that would separate "the plan is now bounded" from "Wednesday's window
is small."

## Section D — the superseded conclusion, and why it was wrong

**The first draft concluded:** the park's first conjunct ("a desk route over
the 25 s read budget") is measured false, therefore delete the park.

**It is not measured false. It was not exercised.** The measurement was taken
in the one regime where the budget was known in advance not to fire, and the
draft said so in its own caveats and then did not let that reach its
conclusion.

The record contains **two** budget events, not one. The draft mentioned only
the first:

1. **2026-09-15, `/api/slate?league=...`** — a plan defect. Fixed, deployed,
   pinned by a test. §C.
2. **2026-09-10, `/api/parlays`** — **503 `read_budget_exceeded`**, after two
   full-table `GROUP BY`s over the 10M-row `fair_prices` evicted the page
   cache; `ladder_candidates` then took **74.8 s cold** in the container
   (3x the budget) against 2.15 s warm. Load was 0.13; nothing was broken.

The second is **not fixed and is structural**: `warm_read_path.py:11-14` — 2.0 GB
of RAM, no swap, a 5.43 GB database, a page cache topping out near 1.49 GB, so
**at most ~27% of the file can ever be resident**; `:31-34` — "a long enough
idle period, or a big enough read elsewhere, evicts this again"; `:17-19` —
"every restart is a coin flip on a 503, and restarts are not rare." It also
reaches the park's *second* conjunct, since the trigger was full-table reads
over `fair_prices`.

**Two further corrections to the draft:**

- It called the park "ADR 0159's". ADR 0159 contains no park — at `:101` it
  *refuses* the index "on a measurement", and its "what this does not decide"
  lists "whether `ANALYZE` ships". The park with the conjunction lives at
  `tasks/NEXT.md:341`.
- It called ADR 0159's **3.37x banked as a fact**. It is not, and the ADR says
  so: `:239-241` records that its rehearsal timed the arms ~30 minutes apart,
  while its sibling bench interleaves round-robin because the same query read
  **1,283 ms and 3,904 ms on cache residency alone** — a 3.04x swing, which
  brackets the 3.37x being claimed. What ADR 0159 banks is the *qualitative*
  finding that live has no table statistics at all. Substituting a contaminated
  magnitude for it is exactly the failure CLAUDE.md's measurement rules exist
  to stop.

## What this leaves

**The park is NOT deleted by this document.** Disposing of a queue item that
encodes a condition, on evidence that does not establish the condition is
false, is the decay pattern CLAUDE.md workflow step 7 and `tasks/lessons.md`
2026-09-16 describe — and deleting it is precisely the thing a session can
execute alone.

There is a **better argument for retiring the ANALYZE line** which this
measurement did not produce and which does not depend on a warm box. ADR
0159:230:

    CANDIDATE_SQL   1,177.0 ms -> 1,157.5 ms   1.02x   plan UNCHANGED

`CANDIDATE_SQL` is the statement behind `/api/parlays` — the desk's slowest
route and the one with a real 503 history. A plan-unchanged ~1.0 ratio is not a
magnitude claim, so it does not inherit the interleaving defect the way the
3.37x does; ADR 0159 itself leans on that same line to conclude ADR 0134's
`MULTI-INDEX OR` survives `ANALYZE`. That argument survives a cold box, a
Saturday NCAAF slate and a page-cache eviction.

It is still a disposal, and ADR 0159 leaves "whether `ANALYZE` ships"
explicitly undecided, so it is Joe's:

**Question for Joe: the ANALYZE park's trigger has been hit twice — once by a
plan defect now fixed, once by a page-cache eviction that is structural on a
2 GB box — so should the park be deleted, or rewritten to name the cold and
evicted path it was really about? — #51**
