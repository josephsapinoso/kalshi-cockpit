-- Count the tests, then ask whether the findings beat chance.
--
-- This mart exists because of a specific, reproducible embarrassment. The demo
-- history is generated with **no edge whatsoever** -- every outcome drawn at
-- exactly the implied probability. Running the calibration mart over it
-- produced:
--
--     bucket  n   implied  actual   gap     sig
--     73.0    46  0.730    0.522    -20.8   True
--
-- A 20-point "finding", significant at two standard errors, from pure noise.
-- Every per-cell guard behaved correctly. The noise guard was right, the normal
-- approximation was valid, the standard error was computed under the null --
-- and the conclusion was still wrong, because ten cells were tested and roughly
-- one in twenty clears two standard errors by chance.
--
-- 1,190 category cells in the predecessor project produced dozens of
-- "significant" results this way. A per-cell guard cannot catch it; only
-- counting can.
--
-- This mart is deliberately a single row. It is the thing to read *before* any
-- individual bucket.
--
-- What it counts, and what it still does not
-- ------------------------------------------
-- Every bucketed two-standard-error test in the warehouse: `mart_calibration`,
-- `mart_clv_by_bucket` and `mart_suppression_audit`. `tests_by_source` shows
-- the split so the total is checkable rather than merely asserted.
--
-- It does **not** count `gate.py`'s CLV noise guard, and that is deliberate
-- rather than an omission: the gate is evaluated continuously against a growing
-- record, which is a different multiplicity problem along a different axis, and
-- it carries its own always-valid bound (`gate.always_valid_multiplier`).
-- Folding it in here would apply two corrections to one test.
--
-- `analysis/validate.py` runs its tests over the same underlying observations
-- as these marts, so counting both would double-count the same cells.

-- **Every mart that runs a two-standard-error test is counted here.**
--
-- This originally counted `mart_calibration` alone, while `mart_clv_by_bucket`
-- and `mart_suppression_audit` ran their own significance tests uncounted. The
-- p-value below is monotone in `n_tests`, so undercounting makes findings look
-- *more* significant -- the flattering direction, and the exact failure this
-- model exists to prevent, committed by the model itself.
--
-- Findings are read from each mart's OWN published conclusion rather than
-- recomputed here. Recomputing from rounded output could count a finding the
-- mart did not report, or miss one it did, and a counter that disagrees with
-- the thing it counts is worse than no counter.
with per_source as (

    select
        'calibration' as source,
        count(*) filter (where normal_approx_valid) as n_tests,
        count(*) filter (where is_distinguishable) as n_findings
    from {{ ref('mart_calibration') }}

    union all

    select
        'clv_by_bucket',
        count(*) filter (
            where n >= {{ var('min_scored_recommendations') }}
              and stderr_cents is not null
        ),
        count(*) filter (where is_distinguishable)
    from {{ ref('mart_clv_by_bucket') }}

    union all

    -- Both directions are findings. A rule whose rejections beat the close
    -- ("REVIEW") and one whose rejections underperformed ("protective") are
    -- each a cell that cleared two standard errors; only "neutral" did not.
    select
        'suppression_audit',
        count(*) filter (where n_rejected >= 30 and stderr_cents is not null),
        count(*) filter (
            where verdict like 'REVIEW:%' or verdict like '%protective%'
        )
    from {{ ref('mart_suppression_audit') }}

),

tested as (

    select
        -- Cast at the source: DuckDB's `sum` over BIGINT yields HUGEINT, and
        -- `generate_series` has no HUGEINT overload.
        cast(sum(n_tests) as bigint) as n_tests,
        cast(sum(n_findings) as bigint) as n_findings,
        -- Kept so a reader can see WHERE the tests came from. A single total is
        -- unfalsifiable; the breakdown is checkable against each mart.
        string_agg(
            source || '=' || n_findings || '/' || n_tests, ', ' order by source
        ) as tests_by_source
    from per_source

),

expectation as (

    select
        n_tests,
        n_findings,
        tests_by_source,
        -- Two-sided at two standard errors is alpha ~= 0.0455 under normality.
        n_tests * 0.0455 as expected_by_chance
    from tested

),

-- Probability of seeing at least this many "significant" cells if nothing
-- were real. Computed exactly rather than approximated: with ten tests the
-- normal approximation to the binomial is itself invalid, which would be a
-- particularly embarrassing place to take a shortcut.
--
-- The series is generated to `n_findings - 1` rather than to a hardcoded 200.
-- The old bound silently truncated the sum once the grid grew past it, which
-- inflates `p` toward 1 -- so the bug that hid findings and the bug that
-- invented them were one edit apart.
scored as (

    select
        e.n_tests,
        e.n_findings,
        e.tests_by_source,
        e.expected_by_chance,
        1 - coalesce(
            (
                select sum(
                    pow(0.0455, g.k) * pow(0.9545, e.n_tests - g.k)
                    * exp(
                        lgamma(e.n_tests + 1)
                        - lgamma(g.k + 1)
                        - lgamma(e.n_tests - g.k + 1)
                    )
                )
                from generate_series(0, e.n_findings - 1) as g(k)
            ),
            0
        ) as p_findings_by_chance
    from expectation e

)

select
    n_tests,
    n_findings,
    tests_by_source,
    round(expected_by_chance, 2) as expected_by_chance,
    round(p_findings_by_chance, 4) as p_findings_by_chance,

    -- **Branch on the p-value, not on the count.** The first version compared
    -- n_findings against expected_by_chance and called 1-from-10 "worth
    -- investigating" -- while the p-value sitting in the next column said 0.37,
    -- i.e. a better-than-one-in-three chance of seeing it from nothing. It
    -- computed the right statistic and then ignored it, which is a more
    -- insidious failure than not computing it at all: the correct number was
    -- right there on the dashboard next to the wrong conclusion.
    case
        when n_tests = 0
            then 'no powered tests yet'
        when n_findings = 0
            then 'no findings across ' || n_tests || ' tests'
        when p_findings_by_chance > 0.20
            then 'NOT EVIDENCE: ' || n_findings || ' finding(s) from ' || n_tests
                 || ' tests. Pure chance produces this or more '
                 || round(100 * p_findings_by_chance, 0) || '% of the time.'
        when p_findings_by_chance > 0.05
            then 'WEAK: ' || n_findings || ' finding(s) from ' || n_tests
                 || ' tests (p=' || round(p_findings_by_chance, 3)
                 || '). Not distinguishable from luck.'
        else n_findings || ' finding(s) from ' || n_tests || ' tests (p='
             || round(p_findings_by_chance, 3)
             || '). More than chance predicts -- confirm at a second horizon '
             || 'before believing it.'
    end as verdict

from scored
