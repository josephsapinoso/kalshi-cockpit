# The actionable population, re-audited: a census correction, not a finding about anchoring

**Date:** 2026-08-23 (~16:10Z first run; re-run ~16:55Z captured in full).
**Instrument:** the whitelisted read-only `actionable-audit` query in
`scripts/inspect_live_db.py`, over `flyctl ssh console` against
`/data/cockpit.db` — the same instrument as the 2026-08-16 audit
(`2026-08-16-actionable-population-audit-result.md`). **Predicate:** the
gate's own, byte-identical: `r.suppressed_reason IS NULL AND
r.reference_contracts > 0` (`backend/gate.py:330` =
`inspect_live_db.py:430`). **Audited by the measurement-skeptic before
commit: first draft FAILED on eight defects (D1–D8); this is the corrected
version.** The defect list is preserved in the session transcript; the
headline correction is that the first draft claimed the soft-fallback
explanation was dead, and the skeptic showed the data point the other way
once the base rate is read beside it.

## What this establishes

The whole-table actionable census as of the run instant, with per-row
provenance. **It is a census correction. It is not a finding about
anchoring** — the population that would test the anchoring explanation
(unsuppressed rows split by `anchored_on_sharp`) was not queried.

## Run provenance

`actionable-audit` at the default `--limit 2000` (`DEFAULT_ROW_CAP`). The
query emits **two** sections only — A (decision) and B (fair-value
provenance), `inspect_live_db.py:1461-1526`. Both printed `11 rows` with no
truncation marker, so 11 is the population, not a prefix. The first run's
transcript elided ~5KB mid-output at the session-tool layer (not the
instrument); the re-run was captured whole to a local file and every number
below comes from it.

## The count

**11 rows** satisfy the predicate, across **6 distinct games**, first
written 2026-08-15T19:52:14Z. **`suggested_contracts = 0` on every one** —
these are evidence at the fixed reference sizing only (ADR 0015 §3),
unbuyable at the deployed bankroll, and each row's own `reason_text` renders
"No edge." (the known Board/gate partition mismatch — the deferred `no_edge`
mislabel). Rows are **change events, not polling observations**
(`persist_if_changed`): a re-priced claim writes a new row only when the ask
or fair value moved, and an absent row is not a market that never qualified.

| created (UTC) | game (claim) | rows | league | sharp | books | edge (c) | 4-method spread (pts) | market width (pts) |
|---|---|---|---|---|---|---|---|---|
| 08-15 19:52, 21:56 | BOSPIT (PIT), re-priced twice | 2 | MLB | 0 | 12–13 | 0.35, 0.55 | 0.15, 0.16 | 1.11, 0.57 |
| 08-16 17:06 | WSHNYM batter-hits prop (Over 0.5) | 1 | MLB | 0 | 3 | 0.36 | 0.09 | 2.27 |
| 08-19 00:35, 00:38 | INDDAL (DAL), re-priced twice | 2 | WNBA | 0 | 2 | 3.86, 0.82 | 0.36 | 1.69 |
| 08-19 19:20 | STLCIN (STL), both sides | 2 | MLB | 0 | 15 | 0.22 | 0.07 | 1.92 |
| 08-20 01:26 | INDDAL (IND) | 1 | WNBA | **1** | **2** | 0.49 | 0.43 | 0.77 |
| 08-22 22:21 | INDNY (NY), both sides | 2 | WNBA | **1** | **3** | 0.55 | 0.19 | 2.36 |
| 08-22 23:51 | LVTOR (LV) | 1 | WNBA | **1** | **3** | 1.79 | 1.28 | 1.30 |

(Edge is `edge_tenths`/10; the 4-method spread is max−min of
`p_multiplicative/additive/power/shin` ×100; width is `market_width` ×100.
The two INDDAL entries are one game observed on two days, so 6 games, not 7.
Sharp rows' books: betfair_ex_eu + pinnacle (13977); + matchbook
(18050/18053, 18388).)

## The anchoring split, read against its base rate

- **7 of 11 rows are `anchored_on_sharp = 0`, 4 are `= 1`.** The prior
  paragraph's claim that *every* actionable row is a soft-book fallback is
  superseded **as a description**.
- **Whether ADR 0021's fallback explanation is refuted is NOT answered by
  this run.** Sharp anchoring was **73.0%** of the pinned record (ADR 0021
  §8: 1,141 of 1,564 rows), so 4 of 11 (36%) is sharp
  **under-representation** among actionable rows by roughly 2:1 — a
  direction *consistent with* ADR 0021, not against it. The separating
  measurement is the one the 2026-08-16 audit named and nobody has run:
  split the **unsuppressed** population by `anchored_on_sharp` and report
  the `edge_tenths > 0` rate in each, clustered per game, with the largest
  contributor's share.
- **A sharp anchor is a narrower consensus, not a wider one.**
  `devig.py:288-289` selects sharp books *exclusively* when any is present,
  and ADR 0021 §6 records that this is at most three books. The 4
  sharp-anchored rows are priced off 2–3 opinions against 12–15 for the
  soft MLB rows, with `market_width` measured across the same 2–3. **A
  competing explanation this audit does not rule out: these rows crossed
  because a thin consensus is noisy, not because a better reference quoted
  them.** The table above carries the per-row edge-vs-spread margin for
  whoever runs that separation; note the largest edge in the whole
  population (3.86c, id 12100) sits on a **two-soft-book** consensus, and
  the largest sharp-anchored edge (1.79c, id 18388) is only ~1.4× its own
  four-method spread.
- Three sharp-anchored rows landed on three WNBA games between 08-20 and
  08-22, **two of which (INDDAL, INDNY) share the Indiana Fever**, so by
  team they collapse toward 2. No trend statistic was computed and none is
  claimed; the sport mix of the actionable set also changed inside the
  window.

## Why 3 → 11

Accumulation. `backend/core/devig.py` has no commit since before 2026-08-14,
and no commit in the interval touched the actionable predicate
(`backend/gate.py` was edited three times — `ec44ac4`, `952bb0c`,
`8358728` — all docstring text or the unrelated `_fee_model_verified` fills
filter; `POPULATIONS` untouched). What is **not** established is why the new
rows are WNBA and why 4 are sharp-anchored. This audit cannot say: it
queried only the actionable set, in which WNBA had **two** rows before
08-20, and zero sharp anchors out of two is not an absence of sharp
coverage. WNBA has been in `IN_SCOPE_LEAGUES` since 2026-08-09 and
`ODDS_REGIONS=us,eu` was unchanged across the interval, so the books that
produce a sharp anchor were purchasable throughout. The competing
explanation — WNBA was always sharp-anchored where those books quoted, and a
few rows simply crossed the threshold — predicts everything observed here.
Separating them needs `anchored_on_sharp` by league and day over the whole
`fair_prices` table, which this run did not take.

## What this does not establish

- Not that the strategy has started finding edge: 6 games against the
  registered floor of 300 actionable games (`docs/adr/0005`), and the
  actionable predicate still carries no multiplicity correction while the
  runner re-evaluates ~100 candidates every 900s against a growing record
  (2026-08-16 audit §7C).
- Not a rate: the population spans **eight days** (08-15 19:52Z to the run),
  only **five** of which carried any row (08-15: 2, 08-16: 1, 08-19: 4,
  08-20: 1, 08-22: 3), and two of those five contributed 7 of the 11. No
  per-day figure is meaningful.
- Not anything about anchoring as a cause — see above, twice.
- Not that any row would have been profitable: no CLV or settlement join was
  taken here.
