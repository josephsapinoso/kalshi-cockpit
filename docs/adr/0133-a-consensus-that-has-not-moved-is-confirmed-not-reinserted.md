# ADR 0133 — A consensus that has not moved is confirmed, not re-inserted

**Status:** Accepted, 2026-09-09.
**Date:** 2026-09-09.
**Supersedes nothing.** Extends ADR 0070 (the `oldest_book_age_ms` freshness
input) and follows the naming and shape of ADR 0055, which did the same thing
to `kalshi_quotes` a month earlier.

## 1. The finding

`write_fair_price` (`backend/runner.py`) ended one `INSERT INTO fair_prices`
per outcome, unconditionally, on every call. `run_pricing_pass` is reached
from both the 900s full pass and the 15s quote pass
(`scripts/run_loop.py:1441` and `:1480`), so the consensus was re-derived and
re-inserted roughly every 15-20s regardless of whether it had moved.

Measured on live, three windows, 2026-09-09, an MLB slate — duplication with
key `(link_id, market, outcome_name, outcome_description, outcome_point)`,
payload the ten non-identity, non-timestamp value columns:

| window | span | passes | passes/hour | transitions | UNCHANGED |
|---|---|---|---|---|---|
| A (newest) | 3.98h | 414 | 104.0 | 199,506 | 99.73% |
| B | 5.15h | 420 | 81.6 | 199,504 | 99.61% |
| C (~22h old) | 2.01h | 392 | 195.0 | 199,488 | 99.75% |

`h2h` and `spreads` agree to 2dp in every window. 344 of 494 keys changed zero
times in window A; the largest single key accounts for **~14 of the ~539
changed transitions in window A (2.6%)** — enough to rule out gross
concentration in one market, not enough to characterise moderate
concentration, and not measured per key elsewhere. `fair_prices` plus its two
indexes were 2.41 GB — 47.5% of a 5.07 GB database.

**This table does not support an inferential claim, and none is made.** The
three windows are not `n = 3`: they are one calendar day, so the cluster the
registration would fix is `G = 1`. The 494 keys inside a window are not 494
independent observations either — the CLV registration's cluster is
`link_id`, and the per-`link_id` view of this duplication rate was never
taken. **Do not restate 99.7%, or any figure in the table above, as a rate
that holds on an NFL Sunday** — the window-profile is exactly the thing that
changes most between an MLB weekday and a Sunday slate carrying kickoff
clusters, and this measurement covers neither.

**The identity used above is the one this ADR implements, and an earlier
draft used a four-column key that omitted `outcome_description`.** That key
interleaves two different players priced at the same line in the same game —
`outcome_name` alone is only `"Over"`/`"Under"` on a prop — and scores their
distinct rows as "changed" relative to each other. The error runs *against*
the 99.7% finding, so it is a **floor** on the true duplication rate under the
five-column identity, not a measurement of it. `docs/measurements/
2026-09-01-preregistration-fair-prices-downsample.md` §F6 fixes the same
five-column identity byte-for-byte (`(link_id, market, outcome_name,
outcome_description, outcome_point)`) as `backend/parlays.py`'s
`CANDIDATE_SQL` partition — this decision matches both.

## 2. What was rejected

**Option 1 — freeze both `computed_ms` and `oldest_book_age_ms`, add only a
confirmation timestamp.** Looks right because the pair telescopes today: a
pass at `T` records `computed_ms=T, oldest=T-U`, so live age is always
`now - U`. It is wrong, on a separate live measurement: over 4h of h2h data,
3,360 (event, book, outcome) series, `book_updated_ms` **advanced** on 19,643
of 19,689 consecutive pairs where the price did **not** move (99.8%, median
advance 646s), and zero pairs where the price moved and `book_updated_ms`
stayed put — so `book_updated_ms` is a genuine freshness stamp, not a copy of
the price. The odds feed refetches every ~10 minutes (28 distinct fetch
instants in 6h, p50 gap 615s), so the books get *fresher* roughly every ten
minutes while their prices sit still. A frozen `oldest_book_age_ms` never
learns that: the reported age grows without bound and any consensus held
longer than ~15 minutes gets refused as stale. With 344 of 494 keys unchanged
across 4 hours in the finding above, that empties the ladder — ADR 0055's
own failure mode ("measuring from `observed_ms` would refuse 84.5% of the
slate as stale") arriving by a different route.

**Option 2 — freeze `computed_ms`, overwrite `oldest_book_age_ms` in place.**
Double-counts elapsed time: `(now - T0) + latest_oldest`, where `latest_oldest`
already includes the time since `T0`. Overstates staleness, in the direction
that would refuse a fresh row.

## 3. The decision

Two pairs, each internally consistent because both members of each pair are
stamped at the same instant:

- **`computed_ms` and `oldest_book_age_ms` freeze at first appearance.** Never
  updated after the row is written. `recommendations.fair_price_id` points at
  this row, and this pair is what preserves "when did this consensus first
  appear" — the fact `write_fair_price`'s own docstring already promised
  before this change.
- **`confirmed_ms` and `confirmed_oldest_book_age_ms` are new, nullable,
  and stamped at CONFIRM time** — every pass whose payload matches the most
  recent row for its identity UPDATEs these two instead of inserting a row.
- **Freshness becomes `(now - COALESCE(confirmed_ms, computed_ms)) +
  COALESCE(confirmed_oldest_book_age_ms, oldest_book_age_ms)`**, each member
  coalesced independently. Both members of whichever pair is live come from
  the same instant, so it telescopes correctly and tracks the refreshing
  books. `NULL` means "never re-confirmed" and the fallback to the frozen
  pair is exactly right for a row written once.
- **The existing refusal is preserved.** If the effective oldest-book-age is
  `None`, `_live_age_ms` returns `None` and the ladder refuses the leg. A row
  is never aged zero — load-bearing for every pre-v20 row still on the live
  volume.

### 3.1 Schema (v36)

`fair_prices` gains `confirmed_ms INTEGER` and
`confirmed_oldest_book_age_ms INTEGER`, both nullable, no default, no
backfill — a column step, `backend/store/db.py`'s `_MIGRATIONS[36]`, following
the same idiom as v33/v34 (a pure `ALTER TABLE ADD COLUMN`, no rebuild, undo
is the generic column-drop the migration test infrastructure already infers).
Placed before `anchored_on_sharp` in `schema.sql`, not after it, for the same
reason `oldest_book_age_ms` sits where it does: the wind-back test drops
migrated columns from the live table, and `anchored_on_sharp` is kept the
true last column, with no comment directly above it, so it stays droppable.

**Naming precedent, and which one was followed.** ADR 0055 added a single
bare `confirmed_ms` to `kalshi_quotes`, distinguishing it from `observed_ms`
("when this price FIRST appeared"). `recommendations` instead has
`last_confirmed_ms` / `last_confirmed_quote_age_ms` /
`last_confirmed_odds_age_ms` (`engine.confirm_recommendation`,
`gate.live_ages`) — a `last_confirmed_` prefix. This change follows the
**bare** style: `fair_prices` already distinguishes the frozen member by name
(`computed_ms`, not `created_ms`), so there is only one "confirmed" quantity
per column here, never a "first" and a "last" spelling of the same word the
way `recommendations` needed disambiguating from a plain `confirmed_*` that
did not yet exist on that table. `recommendations`' three-column shape is the
closer precedent for *needing a pair rather than a single column* — a
confirmation there is a complete re-statement about one instant, both ages or
neither, for exactly the same reason `oldest_book_age_ms` cannot be updated
alone here.

### 3.2 `write_fair_price` (`backend/runner.py`)

For each outcome: look up the most recent existing row sharing its identity;
if every payload column matches, `UPDATE` that row's confirmation pair and
return its existing id; otherwise `INSERT` as before. The `{outcome: id}`
contract callers depend on (`recommendations.fair_price_id`) is unchanged.

**Every SQL string touching the column list is built from one tuple.**
`_FAIR_PRICE_INSERT_COLUMNS` (17 columns) is the single source; the identity
(`_FAIR_PRICE_KEY_COLUMNS`, 5), the frozen pair
(`_FAIR_PRICE_FROZEN_COLUMNS`, 2) and the payload
(`_FAIR_PRICE_PAYLOAD_COLUMNS`, 10, computed as the remainder) all derive from
it, and both the `INSERT` and the lookup's `WHERE` clause are assembled from
these tuples rather than hand-typed a second time. This is deliberate past
what was asked: an earlier draft hand-typed the lookup's `WHERE` clause
against the five key columns directly, and a test that monkeypatched
`_FAIR_PRICE_KEY_COLUMNS` to simulate the four-column mistake in §1 passed
for the wrong reason — the hand-typed SQL never read the tuple, so the
"mutation" changed nothing. Building the `WHERE` clause from
`_FAIR_PRICE_KEY_COLUMNS` (`" AND ".join(f"{c} IS ?" ...)`) closed that gap:
the same tuple that documents the identity is now the only thing that can
produce it. `IS`, not `=`, on every key column, including the three that are
never NULL — one operator for the whole key rather than a per-column branch
to keep in sync, and it is load-bearing for `outcome_description` and
`outcome_point`, both NULL on every team-market row.

### 3.3 `_live_age_ms` and the ladder query (`backend/parlays.py`)

`_live_age_ms` implements the independent-COALESCE formula in §3. The
ladder's `CANDIDATE_SQL` now selects `confirmed_ms` and
`confirmed_oldest_book_age_ms` from `fair_prices` (both the outer and the
windowed inner `SELECT`), so the row leaving the query carries what the
formula needs. Its byte-identical copy in
`scripts/inspect_live_db_parlays.py` (`_SQL_PARLAY_CANDIDATES`, pinned equal
by `tests/test_inspect_live_db.py`) was updated in lockstep.

### 3.4 The scan floor is now three terms, not two

`ladder_candidates`' SQL floor (`_CANDIDATE_SCAN_FLOOR_MULTIPLE *
max_odds_age_ms`, documented as "changes no output") stops being able to make
that promise. It assumed `computed_ms` tracks freshness — true only while
every pass re-inserted, so an old `computed_ms` meant a genuinely old,
downstream-refused row. After dedupe, a row can be confirmed-fresh every pass
for as long as a game stays on the desk while carrying whatever `computed_ms`
it was first written with, which can be days before kickoff.
`ladder_candidates` never bounds `o.commence_ms` by any card horizon in SQL
(that cut is in Python, after this query), so the real ceiling is how far
ahead a game can already be tracked: ADR 0099 measured kickoffs "from three
hours to eight days out" on live and caps `within_hours` at 168 (7 days). A
new floor, `_CANDIDATE_SCAN_DEDUPE_FLOOR_MS = 9 days`, is combined with the
existing multiple via `max()` — one day of margin past the observed eight,
never replacing the multiple, which still bounds a row that has never been
confirmed. The predicate stays `f.computed_ms >= ?`, not a `COALESCE`, so
`idx_fair_market_computed` (`market, computed_ms DESC`) keeps serving it as a
seek; widening the floor is nearly free now that dedupe cuts what it scans by
the same ~99.7% (a floor, per §1) the duplication measurement found.

## 4. What this forecloses

**A change-only insert destroys forward what the downsampler destroys
backward, and this is a real, permanent cost, not a footnote.**
`docs/measurements/2026-08-10-sharp-anchoring-census.py:177-191` reconstructs
"which odds instant did the runner actually consume" by reading every
`fair_prices` row's `computed_ms` and matching it to the newest
`odds_snapshots.fetched_ms` at or before that instant — the technique behind
ADR 0021 §8's headline figure, that *"this looks like Kalshi"* holds on
1,141 of 1,564 rows (73.0%). That technique needs one row per pass. A pass
that re-derives an unchanged consensus now leaves no row at all — only a
timestamp update on the row from whenever the price last actually moved — so
the odds instant behind that pass is gone from the record the moment the pass
completes, not merely thinned or approximated. At the measured 99.6-99.75%
confirmation rate, that is the overwhelming majority of the evidence a future
instance of this exact census would need to re-run. **No mitigation is
proposed here.** A future measurement that needs per-pass odds-instant
provenance will not find it in `fair_prices` for any pass after this ADR that
confirmed rather than inserted, and should look for `confirmed_ms` transitions
as a lower-resolution substitute before assuming the question is unanswerable.

## 5. What this does not establish

- **A duplication rate for any slate but the one measured.** §1's numbers are
  11.1 hours on one MLB weekday. Nothing here says what an NFL Sunday's
  kickoff-clustered window profile does to them, and CLAUDE.md's own account
  of the kickoff-window loop (67% of a month's odds spend, seven calls a
  cluster) suggests the profile is exactly what changes most.
- **That the database shrinks.** `auto_vacuum` is SQLite's default (0/NONE)
  on this database — never set otherwise anywhere in `backend/store/db.py` —
  so freed pages return to the file's own freelist, not to the filesystem;
  only a `VACUUM` gives bytes back to the OS. **This changes the SLOPE, not
  the level**: `fair_prices` stops growing at ~99.7% of its previous rate
  from the moment this ships, and the 2.41 GB already on disk stays exactly
  where it is until a `VACUUM` this ADR does not authorise.
- **Anything about the CLV signal or the gate.** No file under `backend/odds/`
  and not `backend/scheduler.py` was touched; `tests/test_fair_price_dedupe.
  py::TestTheFreezeIsRespected` checks that mechanically against this lane's
  diff rather than asserting it. Pass cadence and pass count are unchanged —
  `write_fair_price` is called exactly as often as before, from exactly the
  same two call sites, and the dedupe decision (`INSERT` vs. confirm) happens
  entirely inside it, invisible to `run_pricing_pass` / `run_quote_pass` and
  to everything in `backend/odds/timing.py` that decides when to spend a
  credit.
- **That the identity used here is exhaustive.** It is the registered
  identity for a downsample rule that has never run live (§1's pre-existing
  `docs/measurements/2026-09-01-preregistration-fair-prices-downsample.md`),
  reused here because it is the one this codebase has already committed to
  in two other places (`CANDIDATE_SQL`'s partition, the registration's D4).

## 6. How it was verified

Every guard below was disabled and watched red before being restored:

- **The five-column identity.** Monkeypatching `_FAIR_PRICE_KEY_COLUMNS` down
  to four columns (dropping `outcome_description`) made
  `test_a_four_column_key_would_collide_the_two_players` fail exactly as
  predicted — re-confirming one player's row found the other player's more
  recent one, saw a payload mismatch on the description itself, and minted a
  third row instead of confirming the first.
- **`IS` vs. `=` on the identity.** Discovered mid-implementation: the first
  draft built the lookup's `WHERE` clause by hand, so the identity-mutation
  test above passed for the wrong reason (the hand-typed SQL never read the
  mutated tuple). Rebuilding the `WHERE` clause from `_FAIR_PRICE_KEY_COLUMNS`
  itself made the same mutation test fail for the right reason, and
  `test_moneyline_dedupe_works_despite_null_outcome_point` pins that a
  moneyline row (NULL `outcome_description` and `outcome_point`) still
  dedupes against itself.
- **The derived payload comparison.** Monkeypatching `_FAIR_PRICE_PAYLOAD_
  COLUMNS` to drop `book_count` made
  `test_dropping_book_count_from_the_payload_hides_a_real_change` fail: a
  real `book_count` change was silently confirmed instead of recorded, and
  the stale count stayed in the row. `test_a_book_count_change_with_the_
  same_prices_is_recorded` is the same scenario with the guard intact.
- **The COALESCE fallback in `_live_age_ms`.** Read directly against a
  never-confirmed row, a confirmed row, and a pre-v20 row with no age
  recorded on either pair (`TestLiveAgeUsesTheFresherOfTheTwoPairs`).
- **The widened scan floor.** `TestAConfirmedRowSurvivesAnOldComputedMs`
  seeds a row five days old by `computed_ms` (past the old 2-hour floor by
  three orders of magnitude, inside the new ~9-day one) and confirmed 20s
  ago; it is served, not counted `stale_consensus`. Its control — the same
  age with no confirmation — is refused, proving confirmation buys the
  freshness rather than merely sitting inside the wider floor.
- **The `CANDIDATE_SQL` index seek.** `tests/test_ladder_query_is_indexed.py`
  (unmodified) still asserts `SEARCH f USING INDEX idx_fair_market_computed
  (market=? AND computed_ms>?)` after the two new columns were added to both
  the outer and inner `SELECT`.
- **`scripts/inspect_live_db_parlays.py`'s copy.** `tests/test_inspect_live_
  db.py::TestTheCandidateScanCopyDoesNotDrift` caught the drift immediately
  after `CANDIDATE_SQL` changed; the copy was updated to match byte-for-byte.
- **The freeze.** `tests/test_fair_price_dedupe.py::TestTheFreezeIsRespected`
  diffs this lane against its merge-base with `main` and asserts no path
  under `backend/odds/` and not `backend/scheduler.py` appears — skips rather
  than fails if git cannot answer, matching
  `tests/test_parallel_lanes_do_not_collide.py`'s posture for the same
  reason.

Full suite: `.venv\Scripts\python.exe -m pytest -q` — see the session record
for the count. `scripts/inspect_live_db_parlays.py`'s `_SQL_PARLAY_CANDIDATES`
was the one file outside this ADR's owned list that needed a mechanical
update to keep the suite green, and is called out here rather than left
unexplained in the diff.
