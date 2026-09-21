# 2026-09-21 — `kalshi_quotes` is what grew, its prune is healthy, and the mechanism is NOT established

Ticket #58. Three live readings taken 2026-09-21 between 13:56Z and 14:40Z,
on live `git_sha` `f42bb41e…` then `8c82476703ff7bc1759fe2e9202112a78c592461`.

**Audited by `measurement-skeptic` before entering the record, and this
document is the SECOND draft.** The first draft claimed the flagged
~580 MB/day growth rate had been falsified, and reframed it as "only 1.8×
the registered rate". Both claims were wrong and both ran in the flattering
direction, on good news. §2 and §5 below are the corrected versions; §7
records what the audit caught, because the corrections are more instructive
than the finding.

**One-line result.** The 1.24 GB is real and inside `cockpit.db`. About 65%
of it is **`kalshi_quotes`**, whose prune is provably healthy. Two mechanisms
could produce that and **this reading cannot separate them**: a permanently
growing prune-exemption set, or page bloat in a continuously pruned
random-order index. The growth rate itself is **not** re-measured here.

## What this does not establish

- **Nothing about the growth rate.** §2's 26.7 MB/day is a **selected
  extremum** — one interval, chosen because it was the cheapest moment to
  spend a cache flush, which is the same thing as the quietest. It bounds a
  floor and is not a rate.
- **Not the mechanism behind `kalshi_quotes`.** §5 names two sufficient
  explanations and no separating observation was taken.
- **No multiplicity correction is carried**, and ten hypotheses were touched
  by three readings (§6).
- **Nothing about what may be deleted.** Size is not expendability. This
  document makes no retention recommendation; that is Joe's, on #122.
- **Nothing about the container root**, which the record says is the binding
  filesystem. §1 walks `/data` only.

## 1. The bytes are inside the database — two hypotheses dead

`scripts/inspect_live_disk.py --json` on `/data`, 13:56Z. Free — `statvfs`,
`walk`, `stat`, and it never opens a file it lists — so it was the right
first read and cost the desk nothing.

    cockpit.db       7,717,519,360
    cockpit.db-wal       3,547,352
    cockpit.db-shm         131,072
    (5 more files, 4.1 MB total)
    walked_bytes     7,723,906,551   walked_files 8   walk_errors 0
    unaccounted      882,350,601     reserved     882,278,400

- **A WAL that could not checkpoint** — proposed on the specific mechanism
  that the 2026-09-18 session ran two full `dbstat` walks, each holding a
  read transaction, and a WAL cannot checkpoint past its oldest reader.
  **Dead: the WAL is 3.4 MB** against a 1.24 GB question, a 350× gap. For
  scale the largest WAL this record has seen is 179,731 KiB
  (`backend/store/volume.py`).
- **A leftover `VACUUM INTO` copy.** Dead: 8 files, all accounted for.

`unaccounted_bytes` matches `reserved_bytes` to 72,201 bytes, so no
deleted-but-still-open file holds space — the ext4 root reserve #92/#94
closed, unchanged.

## 2. A third file-size point bounds the FLOOR. It does not falsify the 580

| when | `cockpit.db` bytes |
|---|---|
| 2026-09-18 | 6,476,369,920 |
| 2026-09-20 23:50Z | 7,701,811,200 |
| 2026-09-21 13:56Z | 7,717,519,360 |

The last interval is 15,708,160 bytes over 14.1 hours ≈ **26.7 MB/day**.

**That interval is Sunday 19:50 ET → Monday 09:56 ET** — 2026-09-21 is a
**Monday**. It begins after the NFL Sunday slate has settled and ends before
Monday Night Football: the quietest 14 hours of the American football week.
The window flagged at ~580 MB/day (2026-09-18 → 2026-09-20 23:50Z) contains
**the entire Saturday college slate and the entire Sunday NFL slate**.

Both growing tables are duty-cycled to game action, for reasons already in
the repo:

- `kalshi_quotes` is a **change log** — `schema.sql:167-175`, ADR 0055: a row
  is written only when the quote *moves*. Overnight with nothing live, the
  writer re-confirms in place (`confirmed_ms` bumped, no new row) and inserts
  approach zero. This is the table carrying 65% of the growth.
- `odds_snapshots` falls to the hourly floor when unattended (ADR 0071 §2.6),
  and the kickoff-window loop — 67% of September's spend — fires **zero**
  times in that window.

**So a 22× ratio between "both weekend slates" and "the overnight trough" is
what a *stationary* recorder with this duty cycle predicts.** The reading
cannot distinguish "580 was a burst" from "580 is the weekend and 26.7 is the
trough of the same unchanged regime." 26.7 bounds the floor of the current
regime and says nothing about its mean.

**The first draft's re-framing of the ratio was itself wrong, in the
flattering direction.** It called 580 "1.8×, not 5–7×" by comparing against
`CURRENT_GROWTH_RATE = 326.6 MB/day` (`backend/store/volume.py:149`),
described as "the constant the system actually runs on". But that constant
was measured **2026-09-09, before ADR 0133's dedup**, over `n = 8.138 days`,
and its own comment says it is *"expected to move again — another lane's
`fair_prices` write-dedupe is projected to cut realised growth to roughly
142 MB/day … and when it does, this is the only line that needs editing."*
The dedup has shipped and §3 confirms `fair_prices` is flat, so 326.6 is a
**known-superseded pre-dedup figure that nobody has edited down**. Against
the post-dedup expectation (~142) and the measured floor (82.5), 580 is
roughly **4×–7×** — which is approximately what the thirty-ninth session
said. The correction was not a correction.

(326.6 is also measured on `db_kb + wal_kb`; this table is bare `cockpit.db`.
Immaterial at a 3.4 MB WAL, but not like-for-like.)

**What would settle it:** phase-matched readings — `db-growth-by-table` at the
same clock time on consecutive days, and a file-size point **7 days** after an
earlier one, so the window holds exactly one of each weekday. The `db_kb` pass
log cannot supply it (`RSS_LOG_CAP_BYTES` holds 1–2 days, `volume.py:69`).

## 3. Where the bytes are

`inspect_live_db.py db-sizes --i-accept-the-cache-flush --limit 40`, ~14:05Z.
Taken deliberately, once, and announced before it was spent.

The 2026-09-18 doc uses the same convention (`table | indexes | total`,
decimal GB) and the same file quantity, so the comparison is like-for-like.
`_q_db_sizes`: *"Sum the table and its indexes before concluding what a table
costs."*

| family | 2026-09-18 | 2026-09-21 | delta |
|---|---|---|---|
| `odds_snapshots` (+5 indexes) | 2.60 GB | 2,854,686,720 | +0.25 |
| `fair_prices` (+3 indexes) | 2.46 GB | 2,461,859,840 | **+0.00** |
| **`kalshi_quotes`** (+`idx_quotes_ticker_time`) | **1.20 GB** | **2,000,084,992** | **+0.80** |
| everything else | 0.22 GB | ~0.199 GB | ~−0.02 |
| **file** | **6,476,369,920** | **7,717,519,360** | **+1.24** |

**The closure is a real check, with one caveat.** The three families sum to
7,316,631,552; the file minus that is 400,887,808, of which the freelist is
201,932,800, leaving ~198,955,008 for everything else. The 28 small btrees
visible in the `--limit 40` output sum to ~196 MB — so the ~78 truncated
btrees hold ~3 MB, and the decomposition closes to within that. The caveat:
`--limit 40` cannot have shown all 118 non-big btrees, so "everything else" is
a visible-sum plus a residual, not a full enumeration.

- **`fair_prices` is flat to the reported precision, which is ±5 MB** on the
  2026-09-18 side (2 d.p. in GB) — about ±2–3 MB/day. That licenses "flat",
  not "contributes nothing". ADR 0133's write-time dedup is doing its job.
- **`odds_snapshots` added 0.25 GB in three days** and **nothing will ever
  remove it** — it remains the only table with no bound at all, which is
  #58's actual substance. See §6.
- **`idx_quotes_ticker_time` alone went 535 MB → 959 MB.**

**The freelist quadrupled and the first draft used it only as a plug.**
12,096 pages / 49.5 MB on 2026-09-18 → **49,300 pages / 201,932,800 bytes**
tonight: +152 MB, about 12% of the whole delta, now free space *inside* the
file rather than record. That is not a footnote — it is direct evidence of the
heavy-deletion regime that §5 turns on.

## 4. The prune is healthy. The exemption is real and unbounded

`inspect_live_db.py prune-frontier --i-accept-the-cache-flush`, 14:09:14Z,
run while the cache was already cold from §3.

    frontier  2026-09-18T14:10:08.170Z     cutoff  2026-09-18T14:09:14.505Z
    backlog_rows 0    prunable_rows 8,557,588    total_rows 11,596,682

**`prune_quotes` is not broken and must not be blamed.** The frontier sits
54 seconds *ahead of* the 3-day cutoff with zero backlog: fully caught up.

`prunable_rows` carries **no age predicate** (`inspect_live_db_feed.py:193`)
— it counts non-exempt rows at any age. So:

    11,596,682 total  -  8,557,588 non-exempt  =  3,039,094 EXEMPT  (26.21%)

`backend/store/retention.py:231` spares any quote whose ticker appears in
`recommendations`. **`recommendations` is never pruned** — zero
`DELETE FROM recommendations` anywhere, and `retention.prune()`
(`retention.py:334`) calls exactly three pruners: quotes, `unmatched_items`,
legacy `unmatched_events`. The exemption set is **strictly monotonic**.

The rule itself is sound — its docstring gives a good reason, that a market
quoted before it was recommended should keep that run for closing-line work.
What has no bound is the *set* it exempts.

**Two properties of the reading worth stating, one protective and one
limiting:**

- **The instrument is self-controlling against the SQL NULL trap.**
  `ticker NOT IN (SELECT …)` yields NULL for *every* row if any
  `recommendations.ticker` is NULL, which would forge `backlog_rows = 0` —
  precisely the reading being treated as good news. `schema.sql:977` declares
  `ticker TEXT NOT NULL`, and `prunable_rows` is 8.56 M rather than 0, so the
  reading is not that artifact.
- **"Non-exempt rows are all within 3 days" is true only of *last-confirmed*
  age.** The predicate is `COALESCE(confirmed_ms, observed_ms)`, and ADR 0055
  bumps `confirmed_ms` **in place** on every re-confirming pass. So a row
  inserted weeks ago whose price never moved stays inside the window for as
  long as its market is polled. There is a **third population** — prunable in
  principle, never prunable in practice — that this reading does not size.

## 5. Which mechanism? NOT ESTABLISHED — two explanations, no separating read

At the family's current average of 172.5 bytes/row (2,000,084,992 over
11,596,682), 0.80 GB is ~4.6 M rows against a 3.04 M exempt population — a
factor of 1.5. **Inverted: the exempt rows alone would account for the whole
delta at 263 bytes/row, only 1.53× the average.** That is the honest way to
put it, and a safety factor of 1.53 does not survive the known uncertainties:

- **An average is not a marginal.** 172.5 is the mean cost of a row in the
  present file, applied to a delta. There is no reason to assume they match.
- **Fragmentation is a complete competing explanation, and the source this
  document cites already raised it about this exact index.** The 2026-09-18
  doc: *"`db-sizes` sums `pgsize` and not `dbstat.unused`, so every
  partially-filled page is charged at full price … `idx_quotes_ticker_time`
  (535 MB, random insert order, continuously pruned) … is exactly that
  shape."* SQLite does not compact on delete, so **bytes-per-live-row rises
  with no new rows at all.**
- **The numbers carry the fragmentation signature.** Index +79.3%
  (535 → 959 MB) against table +57.7% (0.66 → 1.041 GB). Under "more rows,
  same shape" those should track; they diverge by 22 points. Add the
  quadrupled freelist (§3) and fragmentation predicts everything observed.

**Neither explanation forbids anything the other predicts**, and no separating
observation was taken.

**The costliest omission of the session.** The 2026-09-18 doc had already
queued the separating instrument — *"One extra column on the next `db-sizes`
run settles it"*, meaning `dbstat.unused`. Tonight's `db-sizes` was run
**without adding that column**. A full-file walk was spent and the question it
had been queued to answer is still open.

**And `MAX(rowid)` does not separate them either.** `db-growth-by-table`
distinguishes "inserts rose" from "exemption grew" and is **blind to
fragmentation**. So a decision rule of the form *"flat inserts with rising
bytes ⇒ the exemption is the whole story"* would be **wrong** — flat inserts
with rising bytes is the fragmentation signature too, and the more
parsimonious reading.

**The first `db-growth-by-table` reading**, 14:40Z on `8c82476`:

    odds_snapshots   5,429,999
    fair_prices     10,166,319
    kalshi_quotes   64,907,346
    poll_log            34,043

Two facts visible in it, neither obtainable from `COUNT(*)`:

- `kalshi_quotes` has a high-water mark of **64.9 M against 11.6 M live rows**
  — about **53 M rows deleted over its life**, independent confirmation from a
  different measurement that the prune does a great deal of work. `id` is
  `INTEGER PRIMARY KEY AUTOINCREMENT` (`schema.sql:164`), so rowid reuse is
  forbidden and this is a true high-water mark. **Confirm the same declaration
  for `odds_snapshots` and `fair_prices` before differencing those two.**
- `odds_snapshots`' mark (5,429,999) sits essentially at its row count
  (5,426,214, #88's live timing), as "no retention rule" implies.

**Next steps, in order of value:**

1. **Add `dbstat.unused` to `db-sizes`** and re-run. This is the separating
   instrument and it has been owed since 2026-09-18.
2. A second `db-growth-by-table` at **the same clock time** on a following
   day — phase-matched, not adjacent. Free.

## 6. What this changes about the question put to Joe — less than the first draft claimed

**#58's substance survives and he can still answer it as written.** The first
draft said he should not. That was wrong. #58 rests on `odds_snapshots` being
the only table with **no bound at all**, and this reading *confirms* that: it
added 0.25 GB that nothing will ever remove, while `fair_prices` is held by
ADR 0133 and `kalshi_quotes` by a prune that works. A three-day window in
which a *bounded* table grew faster makes the unbounded one the slower
question, not the wrong one.

Two corrections to the first draft's framing, both of which overstated:

- **"`odds_snapshots` is growing at its registered rate" is a denominator
  swap.** The 85–110 band is a **whole-file** rate; `odds_snapshots` has never
  had a registered per-table rate. What was measured is one table taking ~2/3
  of the whole file's registered band by itself. "Not the biggest mover this
  week" is defensible; "at its registered rate" is not.
- **`idx_odds_event`'s 479.6 MB is NOT "a free half-gigabyte".** This record
  has already refused that twice — `tasks/NEXT.md:184-187` (#90 timed the cost
  of having *no* index, which "does not license a drop") and `:251` (a schema
  change against `schema.sql:284`'s standing warning, wanting its own ticket
  and Joe) — and commit `2e66f36` is the case where this repo dropped an
  `odds_snapshots` index for "changes no plan" and had to restore it: *the plan
  was never the cost.* It is an **unmeasured candidate, blocked on a timing**
  (#89, instrument now ticketed as #121).

**What is genuinely new for him** is §4, and it is a different question from
#58's: the exemption rule, not a retention horizon.

Question for Joe: 26.2% of quote rows are exempt from deletion forever because the exemption list is never pruned — amend it, bound the list, leave it, or decide it with #58? — #122

(Expanded: `retention.py:231` spares every quote whose ticker ever appeared
in `recommendations`; `recommendations` has no `DELETE` anywhere, so the
exempt share can only rise. Options and the size caveat are on the ticket.)

Nothing was changed on live tonight beyond #118's flag. No retention rule was
written, no row deleted, no `VACUUM` run.

## 7. What the audit caught, and why it is recorded here

`measurement-skeptic` ran on the first draft before it was committed. It
returned **OVERSTATED — do not enter as written**, and it was right on every
count that mattered:

| claim | first draft | verdict |
|---|---|---|
| §1 bytes are in the DB | supported | **kept verbatim** |
| §2 "26.7 falsifies the 580" | headline | **struck** — selected extremum over the quietest window of the week |
| §2 "580 is 1.8×, not 5–7×" | a correction of the 39th session | **struck** — 326.6 is a pre-dedup constant; the 39th session was approximately right |
| §3 decomposition | supported | kept; exact bytes, freelist movement and the `--limit 40` caveat added |
| §4 prune healthy, 26.2% exempt | supported | **kept and strengthened** (NULL self-control, `confirmed_ms` caveat) |
| §5 "the exemption is insufficient" | a conclusion | **struck** — fragmentation explains it equally |
| §6 "he should not answer #58 as written" | a recommendation | **struck** |
| a ticket for Joe | absent | **#122 opened** |

**Three patterns worth more than the finding:**

1. **The document called 2026-09-21 a Sunday.** It is a Monday. The error was
   not cosmetic: the window was chosen *because* it was cheap, and cheap and
   quiet are the same property here — so the draft used the window's quietness
   as evidence after selecting on it.
2. **The draft's "correction" of the thirty-ninth session's ratio was itself
   the flattering error**, committed in the opposite direction, on good news.
   Three quantities circulate as this project's growth rate and the draft
   picked the one that minimised the gap while accusing its predecessor of
   picking the one that maximised it.
3. **`tests/test_a_question_for_joe_has_a_ticket.py` passed on the first
   draft, vacuously.** It refuses a `Question for Joe` marker that carries no
   number; it cannot refuse a *missing* marker. The guard was green and the
   rule was broken.
