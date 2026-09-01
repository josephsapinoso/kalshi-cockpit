"""Thin `fair_prices` to one row per identity per day. **Off, and dry by default.**

Why this exists
---------------
`fair_prices` is **646,230,016 bytes** and has **no retention rule**. With
`idx_fair_link` and `idx_fair_market_computed` its family is 899,887,104 bytes
-- **37.3% of the whole database file** -- and it took **64.4%** of the organic
growth in the volume clock's 44.4-hour composition window, about **103.9 MB/day**
at the headline rate if that share holds
(`docs/measurements/2026-09-01-the-volume-clock.md`, section 5).

`retention.py` mentions the table once, at `:43`, three lines above a "What this
does NOT do" list that names `odds_snapshots` as deliberately out of scope and
does not name `fair_prices` at all. The table was in the author's hand while the
exclusions were being written and still got neither a rule nor an exclusion.

The rows are there because nothing deleted them. The runner re-evaluates ~100
candidates every 900s, so a market accumulates roughly **96 rows a day**, and
every *registered* analysis reads exactly one of them.

The rule is registered, and this module implements it rather than defines it
-------------------------------------------------------------------------------
`docs/measurements/2026-09-01-preregistration-fair-prices-downsample.md` fixes
the cut **before** anyone saw which rows were inconvenient, because the rule
destroys rows a future measurement would read. `REGISTERED_DELETABLE_SQL` below
is section S1 of that document, **byte-for-byte**, and
`tests/test_fair_price_downsample.py` extracts the fenced block from the
document and asserts equality. The registration's own words: *"The
implementation is checked against this query, not this query against the
implementation."*

A row is deleted only if **every one** of six conditions holds; any single
failure keeps it.

===  ==========================================================================
D1   older than `retention_days` (registered at 14)
D2   not referenced by `recommendations.fair_price_id`
D3   its Kalshi event has at least one `closing_lines` row
D4   not the newest row for its identity within its own UTC day
D5   not the last row at or before `commence - h` for any registered horizon
D6   not the newest row for its identity, ever
===  ==========================================================================

**D4 is what makes this a downsample rather than a delete.** The survivor set is
one row per identity per UTC day, forever: the series thins, it does not end.

**D2 is the one that would have been missed.** Every production read of this
table other than the parlay desk reaches it *only* through
`recommendations.fair_price_id` as a 1:1 `LEFT JOIN` -- `/api/slate`
(`api/routes.py:1371`), `/api/market/{ticker}` (`:1870`), `/api/ledger`
(`:2515`, paged over the **whole** history) and the money path
`store/manual_orders.py:389`. `engine.py:497-501` writes a NEW recommendation
row on every price change, each pointing at that pass's `fair_prices` row, so
the referenced set is genuinely sub-daily. A daily-survivor rule without D2
would dangle `fair_price_id` on every other recommendation, and
`routes.py:6334-6340` says the degradation is silent and wrong in a specific
direction: the screen would publish *"fewer than two devig methods solved"*, a
claim about the devig, when the truth is that there was no fair price to read.

**D3's durable artifact is narrower than it looks.** The obvious candidate is
the Parquet lake and it is not one: `store/publish.py` is a CLI run only in CI
against `data/demo.db` (`.github/workflows/ci.yml:86`) and has never run against
live. `closing_lines` plus the frozen `recommendations` link are the only
durable derived artifacts that exist.

Every failure mode falls toward KEEP
------------------------------------
That is a property of the SQL rather than of this docstring. A `NULL` inside a
`NOT IN` subquery makes the predicate `NULL` rather than `TRUE`, so the row is
not eligible; an `IN` with no match is `FALSE` or `NULL`, likewise. A missing
`event_links` row fails `kalshi_event_ticker IS NOT NULL`. A row with no
computable `commence_ms` never enters `anchor_survivor` -- the one place the
direction is not automatic, which is why prerequisite P5 refuses to arm if such
rows exceed 10%. **An unreadable anchor resolves to keep, never to delete**:
this repo's `None`-never-`0` convention, applied to a destructive rule.

Two flags, and neither default deletes
--------------------------------------
`FAIR_PRICE_DOWNSAMPLE_ENABLED=false` and `FAIR_PRICE_DOWNSAMPLE_DRY_RUN=true`.
A row is removed only when the first is true **and** the second is false -- two
independent environment edits. `plan()` counts what it would free and touches
nothing; `run()` refuses to delete unless `config.deletes` is true.

**Nothing on a disk threshold may arm this.** An automatic deletion fired by a
disk alarm is a guard that goes off at the worst possible moment: unattended, on
a volume already in trouble, with nobody reading the output -- and it converts a
recoverable "extend the volume" into an unrecoverable "the rows are gone".
`backend/store/volume.py` imports nothing from here and this module imports
nothing from it; both directions are asserted over the source in
`tests/test_fair_price_downsample.py`.

What this does NOT establish
----------------------------
The registration's section 9 carries eleven of these. Two must appear here in
full, and the registration says so.

- **9.1 -- A downsampled `fair_prices` cannot support any analysis at sub-daily
  resolution, ever again**, for rows past the window.
  `docs/measurements/2026-08-10-sharp-anchoring-census.py:177-191` walks every
  h2h row and matches each `computed_ms` to its own odds-fetch instant; that
  could not be re-run over any downsampled period. Any future question of the
  form *"how did the consensus move across the game-day"* is gone for those
  rows. This is the price, and it is paid in advance -- which is why the rule is
  registered rather than merely reviewed.
- **9.4 -- It does not establish that deleting rows moves free space at all,
  and this is the most important caveat here.** SQLite returns freed pages to a
  free list, not to the operating system; only `VACUUM` gives bytes back, and
  section 7 of the volume clock shows that option is untested on this box, that
  its temp-file justification is refuted, and that it is worth ~0.56 days.
  `retention.py:48-52` asserts freed pages *are* reused so growth stops without
  a `VACUUM`, while section 5 of the volume clock measures the free list
  **accumulating** at 39.7% of organic bytes, and `n = 1` window cannot separate
  the two. `estimated_freed_bytes` is therefore an upper bound multiplied by an
  unmeasured coefficient in [0, 1]: **if that coefficient is 0, this rule frees
  no filesystem bytes however large the eligible set is.**

And one the timing forces, which changes what the rule is *for*: the rule only
reaches rows older than `retention_days`, so before the 2026-09-17 fill date it
can only ever touch rows written before ~2026-09-03. **The great majority of the
growth remaining between now and the fill is too recent for this rule to reach.**
It is a bound on long-run growth, not a rescue for September, and any write-up
must say which of the two it is claiming.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from ..analysis.clv import CONTROL_HORIZON_HOURS, DEFAULT_HORIZON_HOURS

logger = logging.getLogger(__name__)

_MS_PER_DAY = 24 * 60 * 60 * 1000

#: Every horizon a registered analysis names, in hours -- **imported, never
#: re-typed.** A copy that drifted from `backend/analysis/clv.py` would silently
#: delete the row the registered h2 reading is *defined* as (*"the last admitted
#: `fair_prices` before that anchor"*,
#: `docs/measurements/2026-08-11-preregistration-outcome-scored-leadership.md:529`),
#: with no visible symptom until someone tried to run it.
#:
#: These are asserted equal to the literals hard-coded inside
#: `REGISTERED_DELETABLE_SQL`'s `anchor_survivor` CTE, because section S1 spells
#: them out as a literal set *so that adding one is a visible edit*. The test is
#: what joins the two spellings.
#:
#: `0.0` is falsy and this tuple is iterated, never tested for truth -- the
#: landmine `clv.py:73` records.
CLOSING_LINE_HORIZONS_HOURS: tuple[float, ...] = (
    DEFAULT_HORIZON_HOURS,
    CONTROL_HORIZON_HOURS,
)

#: The `fair_prices` **family** in bytes: the table (646,230,016) plus
#: `idx_fair_link` (133,218,304) plus `idx_fair_market_computed` (120,438,784),
#: measured by `db-sizes` on live at 2026-09-01T~16:40Z. The family and not the
#: table alone, because deleting a row frees its index entries too.
#:
#: Fixed by the registration (section 5), which is why it is a constant here
#: rather than a live `dbstat` read: the estimator was defined before any row
#: was counted, and a figure that moves with the table would let the same
#: eligible fraction produce a different verdict on a different day.
FAIR_PRICE_FAMILY_BYTES = 899_887_104

#: The arming threshold, section 6: 2.00 days of runway at the headline
#: 161.40 MB/day, 35.9% of the family, 50.0% of the table. Below it the verdict
#: is NOT WORTH ARMING **at every value of `retention_days`**, and the answer to
#: the volume clock is an extend.
ARMING_THRESHOLD_BYTES = 322_800_000

#: Section 6's second threshold. If the D4 downsample removes fewer than this
#: fraction of the rows passing D1 and D2 and D3, the verdict is PREMISE
#: REFUTED: the "~96 intra-day re-observations per market" premise does not
#: describe this table and section 5 of the volume clock must be reopened.
T_MECH_THRESHOLD = 0.90

#: Prerequisite P5. If more than this fraction of the rows passing D1, D2 and D3
#: have no computable `commence_ms`, the rule is not armed at any value: the
#: keep set would be dominated by a join failure rather than by the registered
#: rule, and the output could not tell the two apart.
P5_MAX_NO_COMMENCE_FRACTION = 0.10

#: Section 6's registered sensitivity sweep, as a set so it cannot be extended
#: later. Every one of these deletes nothing and cannot arm anything.
SENSITIVITY_RETENTION_DAYS = (7, 21, 28, 60)

#: Rows deleted per statement when armed. `retention.py`'s reason: an unbounded
#: `DELETE` over millions of rows holds the write lock for the whole of it and
#: the next quote pass blocks behind it, turning a disk fix into a latency
#: incident. Smaller than `retention.DELETE_BATCH` because this statement ranks
#: three window functions over the table rather than seeking an index.
DELETE_BATCH = 5_000

#: How long a downsample may hold the pass, in seconds. Checked *between*
#: batches and never inside one, so a `DELETE` is never abandoned mid-statement.
DEFAULT_BUDGET_S = 30.0


# ---------------------------------------------------------------------------
# Section S1, verbatim
# ---------------------------------------------------------------------------
#
# Copied from the registration and pinned to it by test. Do not edit this
# string. Editing the rule means amending the registration first and copying
# the amended text here second; an edit in the other order is the exact failure
# a pre-registration exists to prevent.
REGISTERED_DELETABLE_SQL = """
WITH params AS (
    SELECT
        :now_ms                                  AS now_ms,
        :retention_days                          AS retention_days,   -- registered value: 14
        :now_ms - :retention_days * 86400000     AS age_cutoff_ms
),

-- D5 support. The fixture's earliest recorded start, per LINKED odds event.
-- Byte-for-byte `backend/parlays.py:363-386`, including the linked-event
-- restriction and the deliberate absence of a `commence_ms` filter inside the
-- aggregate (a rescheduled fixture's true earliest start can be in the past).
commence AS (
    SELECT odds_event_id, MIN(commence_ms) AS commence_ms
    FROM odds_snapshots
    WHERE odds_event_id IN (SELECT odds_event_id FROM event_links)
    GROUP BY odds_event_id
),

-- Every fair_prices row, with its identity, its UTC day, its fixture start and
-- its Kalshi event. LEFT JOIN on event_links deliberately: `link_id` is
-- NOT NULL REFERENCES event_links(id) (schema.sql:551), but an orphan must be
-- KEPT EXPLICITLY rather than kept by accidentally falling out of an inner
-- join. `kalshi_event_ticker IS NOT NULL` in the final predicate is that.
base AS (
    SELECT
        f.id, f.link_id, f.market, f.outcome_name, f.outcome_description,
        f.outcome_point, f.computed_ms,
        l.kalshi_event_ticker                                    AS kalshi_event_ticker,
        c.commence_ms                                            AS commence_ms,
        strftime('%Y-%m-%d', f.computed_ms / 1000, 'unixepoch')  AS utc_day
    FROM fair_prices f
    LEFT JOIN event_links l ON l.id = f.link_id
    LEFT JOIN commence    c ON c.odds_event_id = l.odds_event_id
),

-- D2. Every row any recommendation points at. `/api/ledger` pages the whole
-- history, so this set has no time bound and must not be given one.
referenced AS (
    SELECT DISTINCT fair_price_id AS id
    FROM recommendations
    WHERE fair_price_id IS NOT NULL
),

-- D3. Kalshi events that have produced at least one closing line, i.e. that
-- have been consumed into a durable derived artifact. The Parquet lake is NOT
-- one (F5) and must never be added here without re-verifying that it runs.
scored_events AS (
    SELECT DISTINCT m.event_ticker AS event_ticker
    FROM closing_lines cl
    JOIN kalshi_markets m ON m.ticker = cl.ticker
    WHERE m.event_ticker IS NOT NULL
),

-- D4. The newest row for its identity within its own UTC day. Partition copied
-- byte-for-byte from `backend/parlays.py:356-357` (F6), plus `utc_day`.
day_survivor AS (
    SELECT id FROM (
        SELECT b.id,
               ROW_NUMBER() OVER (
                   PARTITION BY b.link_id, b.market, b.outcome_name,
                                b.outcome_description, b.outcome_point,
                                b.utc_day
                   ORDER BY b.computed_ms DESC, b.id DESC
               ) AS rn
        FROM base b
    ) WHERE rn = 1
),

-- D5. The last row at or before `commence_ms - h*3_600_000`, per identity, for
-- EVERY registered horizon. Horizons are clv.py:76 and clv.py:84 (F7), and are
-- enumerated as a literal set so that adding one is a visible edit.
-- Rows with no computable `commence_ms` never enter this CTE and so are never
-- marked survivors here. P5 is what stops that from silently becoming a
-- deletion rule, by refusing to arm if they exceed 10%.
anchor_survivor AS (
    SELECT id FROM (
        SELECT b.id,
               ROW_NUMBER() OVER (
                   PARTITION BY b.link_id, b.market, b.outcome_name,
                                b.outcome_description, b.outcome_point, h.h
                   ORDER BY b.computed_ms DESC, b.id DESC
               ) AS rn
        FROM base b
        CROSS JOIN (SELECT 0.0 AS h UNION ALL SELECT 1.0 AS h) h
        WHERE b.commence_ms IS NOT NULL
          AND b.computed_ms <= b.commence_ms - CAST(h.h * 3600000 AS INTEGER)
    ) WHERE rn = 1
),

-- D6. The newest row per identity, unconditionally. Redundant against D4 as
-- both are written today, and registered separately so an amendment to D4
-- cannot silently remove the guarantee that no identity is ever emptied.
identity_newest AS (
    SELECT id FROM (
        SELECT b.id,
               ROW_NUMBER() OVER (
                   PARTITION BY b.link_id, b.market, b.outcome_name,
                                b.outcome_description, b.outcome_point
                   ORDER BY b.computed_ms DESC, b.id DESC
               ) AS rn
        FROM base b
    ) WHERE rn = 1
)

SELECT b.id
FROM base b
WHERE b.kalshi_event_ticker IS NOT NULL                                    -- orphan link -> KEEP
  AND b.computed_ms < (SELECT age_cutoff_ms FROM params)                   -- D1
  AND b.id              NOT IN (SELECT id           FROM referenced)       -- D2
  AND b.kalshi_event_ticker IN (SELECT event_ticker FROM scored_events)    -- D3
  AND b.id              NOT IN (SELECT id           FROM day_survivor)     -- D4
  AND b.id              NOT IN (SELECT id           FROM anchor_survivor)  -- D5
  AND b.id              NOT IN (SELECT id           FROM identity_newest)  -- D6
ORDER BY b.id;
"""


def deletable_subquery() -> str:
    """Section S1 as something that can be nested. The only permitted change.

    SQLite will not accept a trailing `;` inside `SELECT COUNT(*) FROM (...)`,
    so it is stripped -- and stripped *here*, once, rather than by each caller
    hand-retyping the query. Nothing else about the text is touched, which is
    what lets the test compare the constant to the document byte-for-byte.
    """
    return REGISTERED_DELETABLE_SQL.rstrip().rstrip(";")


def _ctes() -> str:
    """S1's `WITH` block, up to and including `identity_newest`.

    Sliced off the registered text rather than re-typed, so the diagnostics the
    registration *requires* -- the per-condition counts, the per-`link_id` view,
    T-MECH, P5 -- are computed over literally the same CTE definitions as the
    verdict. Two hand-written copies of `day_survivor` is how a report and the
    action it reports on drift apart.
    """
    marker = "\nSELECT b.id\nFROM base b\n"
    head, _, _tail = deletable_subquery().partition(marker)
    if not _tail:
        raise AssertionError(
            "S1's final SELECT could not be located; the registered text "
            "changed shape and every derived diagnostic is now unverified."
        )
    return head


# The rows the age, evidence-join and durable-artifact conditions admit --
# section 6's T-MECH population and prerequisite P5's denominator. `commence_ms`
# and day-survivorship come back per row so both diagnostics read one pass.
_D123_SQL = """
SELECT b.id,
       b.link_id,
       b.commence_ms,
       CASE WHEN b.id IN (SELECT id FROM day_survivor) THEN 1 ELSE 0 END
           AS is_day_survivor
FROM base b
WHERE b.kalshi_event_ticker IS NOT NULL
  AND b.computed_ms < (SELECT age_cutoff_ms FROM params)
  AND b.id NOT IN (SELECT id FROM referenced)
  AND b.kalshi_event_ticker IN (SELECT event_ticker FROM scored_events)
"""

# Section 6 requires the count each condition removes **individually**, so that
# it is visible which one is doing the work. Each column counts rows the named
# condition alone would refuse, over the whole table -- they overlap heavily and
# are not additive, which is the point: a condition doing none of the work looks
# identical to one doing all of it in the eligible count alone.
_PER_CONDITION_SQL = """
SELECT
    COUNT(*) AS base_rows,
    SUM(CASE WHEN b.kalshi_event_ticker IS NULL THEN 1 ELSE 0 END)
        AS kept_orphan_link,
    SUM(CASE WHEN NOT (b.computed_ms < (SELECT age_cutoff_ms FROM params))
             THEN 1 ELSE 0 END) AS kept_by_d1_age,
    SUM(CASE WHEN b.id IN (SELECT id FROM referenced) THEN 1 ELSE 0 END)
        AS kept_by_d2_referenced,
    SUM(CASE WHEN b.kalshi_event_ticker NOT IN
                  (SELECT event_ticker FROM scored_events)
             THEN 1 ELSE 0 END) AS kept_by_d3_unscored,
    SUM(CASE WHEN b.id IN (SELECT id FROM day_survivor) THEN 1 ELSE 0 END)
        AS kept_by_d4_day_survivor,
    SUM(CASE WHEN b.id IN (SELECT id FROM anchor_survivor) THEN 1 ELSE 0 END)
        AS kept_by_d5_anchor,
    SUM(CASE WHEN b.id IN (SELECT id FROM identity_newest) THEN 1 ELSE 0 END)
        AS kept_by_d6_newest
FROM base b
"""

# A pooled number is not a finding until the parts agree. This repo has been
# burned by two WNBA games carrying 41% of a population, so the per-group view
# and the largest contributor's share are required output, not an extra.
_PER_LINK_SQL_TEMPLATE = """
SELECT d.link_id, COUNT(*) AS eligible_rows
FROM ({inner}) e
JOIN fair_prices d ON d.id = e.id
GROUP BY d.link_id
ORDER BY eligible_rows DESC
"""


@dataclass(frozen=True)
class DownsamplePlan:
    """What the rule WOULD remove, and every diagnostic the registration names.

    Nothing here is `0` standing in for an unknown. `estimated_freed_bytes` is
    `None` when `total_rows` is 0, because a fraction with no denominator is not
    the number zero; `t_mech` and `p5_no_commence_fraction` are `None` when
    their population is empty, for the same reason. A 0 in any of those places
    would read as a finding, and the finding it would read as -- "there is
    nothing to gain" -- is the one an absent measurement must not support.
    """

    total_rows: int
    eligible_rows: int
    #: `eligible_rows / total_rows`. A proportion over a **complete
    #: enumeration**: exactly zero sampling error, no standard error, and
    #: printing one would invent a sampling process that does not exist.
    eligible_row_fraction: Optional[float]
    #: `eligible_row_fraction * FAIR_PRICE_FAMILY_BYTES`. **The only estimator
    #: here**, carrying model error rather than sampling error. Its assumption
    #: must be printed on the same line every time: bytes per row are uniform
    #: across the table and both indexes. They are not exactly uniform --
    #: `books_used` is a JSON array whose length varies with book count, and
    #: prop rows carry an `outcome_description` team rows do not.
    estimated_freed_bytes: Optional[int]
    #: Rows passing D1 and D2 and D3: T-MECH's population and P5's denominator.
    d123_rows: int
    #: The fraction of `d123_rows` that D4 removes. Threshold 0.90.
    #:
    #: **This docstring was right and the code under it was backwards.**
    #: Until 2026-09-01 the value assigned was `day_survivors / d123_rows`
    #: -- the fraction D4 *keeps*. A prose caveat cannot catch that; only a
    #: test that runs `plan()` over rows and reads the number back can, and
    #: every assertion in the suite hand-set this field on a constructor
    #: instead. See `TestTMechIsComputedFromRowsAndNotFromAConstructor`.
    t_mech: Optional[float]
    #: The fraction of `d123_rows` with no computable `commence_ms`. Those rows
    #: are KEPT. Threshold 0.10, above which nothing may be armed.
    p5_no_commence_fraction: Optional[float]
    per_condition: dict[str, int]
    #: `(link_id, eligible_rows)`, largest first.
    per_link: tuple[tuple[Any, int], ...]
    closing_lines_rows: int
    scored_event_tickers: int
    cutoff_ms: int
    retention_days: int
    horizons_hours: tuple[float, ...]
    #: True only for the one registered arming value. Every other value is a
    #: sensitivity sweep and cannot arm anything.
    is_registered_value: bool

    @property
    def largest_link_share(self) -> Optional[float]:
        if not self.eligible_rows or not self.per_link:
            return None
        return self.per_link[0][1] / self.eligible_rows

    @property
    def verdict(self) -> str:
        """Section 6's decision rule, in code. Prerequisites are the caller's.

        This deliberately answers only the two thresholds it can compute. P1-P6
        are checked by the harness and reported first, and a NO on any of them
        makes this string void rather than wrong -- which is why it is not
        folded in here, where a caller could read the verdict without them.
        """
        if not self.is_registered_value:
            return "SENSITIVITY - DELETES NOTHING - CANNOT ARM"
        if self.t_mech is None or self.t_mech < T_MECH_THRESHOLD:
            return "PREMISE REFUTED"
        if (
            self.estimated_freed_bytes is None
            or self.estimated_freed_bytes < ARMING_THRESHOLD_BYTES
        ):
            return "NOT WORTH ARMING"
        return "ELIGIBLE TO PROPOSE ARMING"

    def as_dict(self) -> dict:
        return {
            "total_rows": self.total_rows,
            "eligible_rows": self.eligible_rows,
            "eligible_row_fraction": self.eligible_row_fraction,
            "estimated_freed_bytes": self.estimated_freed_bytes,
            "d123_rows": self.d123_rows,
            "t_mech": self.t_mech,
            "p5_no_commence_fraction": self.p5_no_commence_fraction,
            "per_condition": dict(self.per_condition),
            "per_link": [list(row) for row in self.per_link],
            "largest_link_share": self.largest_link_share,
            "closing_lines_rows": self.closing_lines_rows,
            "scored_event_tickers": self.scored_event_tickers,
            "cutoff_ms": self.cutoff_ms,
            "retention_days": self.retention_days,
            "horizons_hours": list(self.horizons_hours),
            "is_registered_value": self.is_registered_value,
            "verdict": self.verdict,
        }


#: The one value the arming decision may be evaluated at. One cell tested, and
#: the multiplicity is 1 by construction because this was named before any of
#: the sweep values was computed.
REGISTERED_RETENTION_DAYS = 14


def plan(conn, *, now: int, retention_days: int = REGISTERED_RETENTION_DAYS):
    """Count what the rule would free. **Deletes nothing, ever.**

    This is the only permitted source of the bytes figure. Every figure this
    project has for `fair_prices` so far is a share of a share taken over a
    44.4-hour window whose accounting is an identity rather than a
    corroboration, and the registration forbids quoting any of them as this
    quantity.
    """
    params = {"now_ms": now, "retention_days": retention_days}
    inner = deletable_subquery()

    total = conn.execute("SELECT COUNT(*) FROM fair_prices").fetchone()[0]
    eligible = conn.execute(
        f"SELECT COUNT(*) FROM ({inner})", params
    ).fetchone()[0]

    d123 = conn.execute(_ctes() + _D123_SQL, params).fetchall()
    d123_rows = len(d123)
    # Index by position, not by key: `sqlite3.Row` is not configured on every
    # connection this is handed, and a `row["..."]` that works in a test and
    # raises on live is a defect this repo has already paid for.
    day_survivors = sum(1 for row in d123 if row[3])
    no_commence = sum(1 for row in d123 if row[2] is None)

    per_condition_row = conn.execute(_ctes() + _PER_CONDITION_SQL, params).fetchone()
    per_condition = {
        "base_rows": per_condition_row[0],
        "kept_orphan_link": per_condition_row[1] or 0,
        "kept_by_d1_age": per_condition_row[2] or 0,
        "kept_by_d2_referenced": per_condition_row[3] or 0,
        "kept_by_d3_unscored": per_condition_row[4] or 0,
        "kept_by_d4_day_survivor": per_condition_row[5] or 0,
        "kept_by_d5_anchor": per_condition_row[6] or 0,
        "kept_by_d6_newest": per_condition_row[7] or 0,
    }

    per_link = tuple(
        (row[0], row[1])
        for row in conn.execute(
            _PER_LINK_SQL_TEMPLATE.format(inner=inner), params
        ).fetchall()
    )

    closing_lines_rows = conn.execute(
        "SELECT COUNT(*) FROM closing_lines"
    ).fetchone()[0]
    scored_events = conn.execute(
        "SELECT COUNT(DISTINCT m.event_ticker) FROM closing_lines cl "
        "JOIN kalshi_markets m ON m.ticker = cl.ticker "
        "WHERE m.event_ticker IS NOT NULL"
    ).fetchone()[0]

    fraction = None if not total else eligible / total
    return DownsamplePlan(
        total_rows=int(total),
        eligible_rows=int(eligible),
        eligible_row_fraction=fraction,
        estimated_freed_bytes=(
            None if fraction is None else int(fraction * FAIR_PRICE_FAMILY_BYTES)
        ),
        d123_rows=d123_rows,
        # `day_survivors` counts the rows D4 KEEPS (rn = 1 per identity per
        # UTC day), so T-MECH -- the fraction D4 REMOVES -- is its
        # complement. This read `day_survivors / d123_rows` until
        # 2026-09-01 and reported the keep rate under the remove label, so
        # the 2026-09-01 deciding run printed 1.32% against a 90% floor and
        # returned PREMISE REFUTED when the true removal rate was 98.68%.
        t_mech=(None if not d123_rows else 1.0 - day_survivors / d123_rows),
        p5_no_commence_fraction=(
            None if not d123_rows else no_commence / d123_rows
        ),
        per_condition=per_condition,
        per_link=per_link,
        closing_lines_rows=int(closing_lines_rows),
        scored_event_tickers=int(scored_events),
        cutoff_ms=now - retention_days * _MS_PER_DAY,
        retention_days=retention_days,
        horizons_hours=CLOSING_LINE_HORIZONS_HOURS,
        is_registered_value=(retention_days == REGISTERED_RETENTION_DAYS),
    )


def run(conn, *, now: int, config, budget_s: float = DEFAULT_BUDGET_S) -> int:
    """Delete what the rule permits. Returns rows removed; 0 unless armed.

    **Two independent refusals, and the first is the one that matters.**
    `config.deletes` is `enabled and not dry_run`, so both the shipped default
    and the intended first deployed step return 0 here without touching a row.
    A single tri-state would put "delete" one typo away from "report".

    **The one deliberate difference from section S1.** The registration says the
    armed rule runs `DELETE FROM fair_prices WHERE id IN (<S1>)` and nothing
    else; this wraps that in a `LIMIT` and a time budget. That changes *which
    rows* not at all -- the population is the same query, unedited -- and
    changes only how many are removed per statement. Without it one `DELETE`
    holds the write lock over millions of rows and the next quote pass blocks
    behind the whole of it, which is `retention.py`'s measured lesson: the first
    live prune stalled the recorder for its entire duration and `recorder.age_ms`
    climbed one second per second while it ran.

    Each batch is its own transaction, so a crash midway leaves the table partly
    downsampled rather than rolled back -- the correct direction, since the rows
    were surplus and resuming removes the rest.
    """
    if not getattr(config, "enabled", False):
        return 0
    retention_days = getattr(config, "retention_days", REGISTERED_RETENTION_DAYS)
    if not getattr(config, "deletes", False):
        # The dry run must be loud. A silent "did nothing" is indistinguishable
        # from a rule that was never wired up, which is this project's most
        # repeated defect.
        report = plan(conn, now=now, retention_days=retention_days)
        logger.info(
            "fair_prices downsample DRY RUN (%s): %d of %d rows eligible, "
            "ESTIMATE %s bytes (uniform bytes/row across table + both "
            "indexes); nothing was deleted.",
            report.verdict,
            report.eligible_rows,
            report.total_rows,
            "UNKNOWN" if report.estimated_freed_bytes is None
            else f"{report.estimated_freed_bytes:,}",
        )
        return 0

    params = {"now_ms": now, "retention_days": retention_days}
    sql = (
        "DELETE FROM fair_prices WHERE id IN ("
        f"SELECT id FROM ({deletable_subquery()}) LIMIT :batch)"
    )
    params = {**params, "batch": DELETE_BATCH}
    deadline = time.monotonic() + budget_s
    removed = 0
    while True:
        cursor = conn.execute(sql, params)
        conn.commit()
        if not cursor.rowcount:
            break
        removed += cursor.rowcount
        if time.monotonic() >= deadline:
            break
    if removed:
        logger.info("fair_prices downsample: removed %d rows", removed)
    return removed
