-- Every mart that runs a significance test must be counted by
-- `mart_multiple_comparisons`.
--
-- This model originally counted `mart_calibration` alone while
-- `mart_clv_by_bucket` and `mart_suppression_audit` ran their own
-- two-standard-error tests uncounted. The p-value is monotone in `n_tests`, so
-- an uncounted mart makes every finding look **more** significant: on the seeded
-- no-edge history, counting 8 tests instead of 11 moved p from 0.401 to 0.311 --
-- a 29% improvement in apparent significance, bought entirely by forgetting to
-- count.
--
-- The source names are listed here independently rather than derived from the
-- model, so deleting a `union all` branch over there fails here. A test that
-- recomputed the total from the same expression would agree with the bug.
--
-- Adding a new mart with a significance test? Add it to the model AND to this
-- list. That is the intended friction: the count is the whole mechanism, and a
-- new test that nobody counts is exactly the failure this file exists to catch.

with expected_sources(source) as (
    values ('calibration'), ('clv_by_bucket'), ('suppression_audit')
),

missing as (

    select
        e.source as failure_source,
        m.tests_by_source as failure_detail
    from expected_sources e
    cross join {{ ref('mart_multiple_comparisons') }} m
    where m.tests_by_source not like '%' || e.source || '%'

),

-- The p-value must remain a probability. The binomial sum was once generated
-- over a hardcoded `generate_series(0, 200)`, which silently truncated once the
-- grid grew past it and pushed p toward 1 -- hiding findings rather than
-- inventing them, but wrong in a way nothing would have reported.
impossible as (

    select
        'p_findings_by_chance' as failure_source,
        cast(p_findings_by_chance as varchar) as failure_detail
    from {{ ref('mart_multiple_comparisons') }}
    where p_findings_by_chance < 0
       or p_findings_by_chance > 1
       or p_findings_by_chance is null

),

-- A finding is a test that cleared the bar, so there cannot be more findings
-- than tests. If this fires, a mart's "powered" condition disagrees with the
-- condition it uses to declare a finding.
inconsistent as (

    select
        'n_findings > n_tests' as failure_source,
        n_findings || ' of ' || n_tests as failure_detail
    from {{ ref('mart_multiple_comparisons') }}
    where n_findings > n_tests

)

select * from missing
union all
select * from impossible
union all
select * from inconsistent
