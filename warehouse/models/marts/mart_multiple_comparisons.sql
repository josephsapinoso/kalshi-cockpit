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

with tested as (

    select
        count(*) filter (where normal_approx_valid) as n_tests,
        count(*) filter (where is_distinguishable) as n_findings
    from {{ ref('mart_calibration') }}

),

expectation as (

    select
        n_tests,
        n_findings,
        -- Two-sided at two standard errors is alpha ~= 0.0455 under normality.
        n_tests * 0.0455 as expected_by_chance
    from tested

),

-- Probability of seeing at least this many "significant" cells if nothing
-- were real. Computed exactly rather than approximated: with ten tests the
-- normal approximation to the binomial is itself invalid, which would be a
-- particularly embarrassing place to take a shortcut.
scored as (

    select
        n_tests,
        n_findings,
        expected_by_chance,
        1 - coalesce(
            sum(
                pow(0.0455, k) * pow(0.9545, n_tests - k)
                * exp(lgamma(n_tests + 1) - lgamma(k + 1) - lgamma(n_tests - k + 1))
            ) filter (where k < n_findings),
            0
        ) as p_findings_by_chance
    from expectation
    cross join (select unnest(generate_series(0, 200)) as k) numbers
    where k <= n_tests
    group by n_tests, n_findings, expected_by_chance

)

select
    n_tests,
    n_findings,
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
