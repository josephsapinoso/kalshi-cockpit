# ADR DRAFT — `fair_prices` is downsampled to daily, behind a flag that is off

- **Status:** Accepted as a *build*, and explicitly **not** as an arming. The
  ordinal is assigned at merge; 0094 is taken.
- **Date:** 2026-09-01
- **Registers:**
  `docs/measurements/2026-09-01-preregistration-fair-prices-downsample.md` —
  the cut is fixed there, in advance, and this ADR may not widen it.
- **Related:** `docs/measurements/2026-09-01-the-volume-clock.md` (why),
  ADR 0054 (the 2026-08-16 volume-full incident), the sibling draft
  `DRAFT-the-volume-alarm-fires-on-free-bytes.md` (which must never call this).

## 1. The problem, stated as bytes

`fair_prices` is **646,230,016 bytes** and has **no retention rule**. With
`idx_fair_link` and `idx_fair_market_computed` its family is 899,887,104 bytes
— **37.3% of the whole database file**. It took **64.4%** of the organic growth
in the volume clock's 44.4-hour composition window, which at the headline
161.40 MB/day is about **103.9 MB/day** if the share holds.

`backend/store/retention.py` mentions the table once, at `:43`, three lines
above a "What this does NOT do" list that names `odds_snapshots` as deliberately
out of scope and does not name `fair_prices` at all. **The table was in the
author's hand while the exclusions were being written and still got neither a
rule nor an exclusion.**

The rows are there because nothing deleted them, not because anything reads
them: the runner re-evaluates ~100 candidates every 900s, so a market
accumulates roughly **96 rows a day**, and every *registered* analysis reads
exactly one of them.

## 2. The decision: downsample to daily, never truncate

A row is deleted only if **every one** of six conditions holds. Any single
failure keeps it. The full statement, with its citations, is §4 of the
registration; the shape is:

| | condition | what it protects |
|---|---|---|
| D1 | older than `RETENTION_DAYS` (registered at 14) | the live desk |
| D2 | not referenced by `recommendations.fair_price_id` | the evidence join |
| D3 | its event has at least one `closing_lines` row | unscored markets |
| D4 | not the newest row for its identity within its own UTC day | daily resolution |
| D5 | not the last row before `commence − h` for any registered horizon | the closing-line anchors |
| D6 | not the newest row for its identity, ever | the desk's fallback |

**D4 is what makes this a downsample rather than a delete.** The survivor set
is one row per identity per UTC day, forever — the series thins, it does not
end. Identity is `(link_id, market, outcome_name, outcome_description,
outcome_point)`, byte-for-byte the partition `backend/parlays.py:355-359` uses,
including `outcome_description`, which is NULL on team markets and load-bearing
on props where `outcome_name` is only "Over"/"Under".

**D2 is the one that would have been missed.** Every production read of
`fair_prices` other than the parlay desk reaches the table *only* through
`recommendations.fair_price_id` as a 1:1 `LEFT JOIN` — `/api/slate`
(`backend/api/routes.py:1371`), `/api/market/{ticker}` (`:1870`), `/api/ledger`
(`:2515`, paged over the **whole** history), and the money path
`backend/store/manual_orders.py:389`. And `backend/engine.py:497-501` writes a
**new** recommendation row on every price change, each pointing at that pass's
`fair_prices` row, so the referenced set is genuinely sub-daily rather than one
row per market per day. A rule that kept only a daily survivor would dangle
`fair_price_id` on every other recommendation, and `routes.py:6334-6340` is
explicit that the degradation is silent and wrong in a specific direction: the
screen would publish *"fewer than two devig methods solved"*, a claim about the
devig, when the truth is that there was no fair price to read.

**D3 is the "already consumed" test, and the artifact is narrower than it
looks.** The obvious durable artifact is the Parquet lake, and it is not one:
`backend/store/publish.py` is a CLI run only in CI against `data/demo.db`
(`.github/workflows/ci.yml:86`) and **has never run against live**. So
`closing_lines` plus the frozen `recommendations` link are the only durable
derived artifacts that exist, and a market with no `closing_lines` row keeps
every row it has.

## 3. It ships OFF, with a dry run, and that is the point

`FAIR_PRICE_DOWNSAMPLE_ENABLED=false` and `FAIR_PRICE_DOWNSAMPLE_DRY_RUN=true`.
**A row is removed only when the first is true and the second is false** — two
independent environment edits, neither of them the default. A single tri-state
`MODE` string would put "delete" one typo away from "report".

The dry run counts the rows and the bytes it *would* free and deletes nothing.
That is not caution for its own sake: it **converts an irreversible decision
into a reversible one, and it produces the byte figure the current estimate does
not have.** §5 of the volume clock is a composition over a 44.4-hour window
whose residual absorbs two indexes never measured on the earlier date, so there
is no arrangement of those numbers under which the accounting would fail to
close — it is an identity, not a corroboration. The dry run is the first
measurement of this quantity that is not a share of a share.

**Arming is a separate decision, needs a named human, and is not authorised
here.** In particular it must **never** be self-arming on a disk threshold. An
automatic deletion fired by a disk alarm is a guard that goes off at the worst
possible moment: unattended, on a volume already in trouble, with nobody reading
the output — and it converts a recoverable "extend the volume" into an
unrecoverable "the rows are gone". `backend/store/volume.py` imports nothing
from `backend/store/fair_price_downsample.py` and the reverse is also true;
both directions are asserted over the source in tests.

## 4. What is given up, permanently, and it is not small

**A downsampled `fair_prices` cannot support any analysis at sub-daily
resolution, ever again**, for rows older than the window. That is the price and
it is paid in advance, which is why the rule is registered rather than merely
reviewed.

Concretely: `docs/measurements/2026-08-10-sharp-anchoring-census.py:177-191`
walks *every* h2h row and matches each `computed_ms` to its own odds-fetch
instant. That is a genuine intra-day time series and it could not be re-run over
any downsampled period. Any future question of the form *"how did the consensus
move across the game-day"* is gone for those rows. The registration's §9 says so
in those words.

What survives: the daily series (D4), every anchor a registered analysis names
(D5), every row any recommendation points at (D2), and every row of any market
not yet scored (D3).

## 5. The caveat that could make the whole thing worthless

**Deleting rows may free zero filesystem bytes.** SQLite returns freed pages to
a free list, not to the operating system; only `VACUUM` gives bytes back, and §7
of the volume clock shows the `VACUUM` option on this box is untested, that its
temp-file justification is **refuted**, and that it is worth about 0.56 days
either way. `backend/store/retention.py:48-52` asserts that freed pages *are*
reused so growth stops without a `VACUUM` — while §5 of the volume clock
measures the free list **accumulating** at 39.7% of organic bytes and §9 calls
that the largest single uncertainty in the document.

So the honest claim for this rule is: **it slows future growth of the largest
table in the system, and it may return no free space at all.** It is not a
substitute for `fly volumes extend`, and the alarm — not this — is what tells
someone to run that.
