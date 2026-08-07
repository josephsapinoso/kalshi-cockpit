-- Closing-line value by the price actually paid, with the noise guard applied
-- in SQL rather than in a comment.
--
-- The column that matters is `verdict`. It is the only thing downstream should
-- render, and it is deliberately a *string* rather than a number: a mart that
-- emits a mean CLV of +0.8c invites a dashboard to plot it as though it means
-- something, whatever the caveat next to it. A cell that cannot clear the
-- guard says so in words that cannot be charted.

with scored as (

    select *
    from {{ ref('stg_recommendations') }}
    where is_scored

),

by_bucket as (

    select
        price_bucket_cents,
        count(*) as n,
        avg(clv_cents) as mean_clv_cents,
        stddev_samp(clv_cents) as sd_clv_cents,
        avg(case when clv_cents > 0 then 1.0 else 0.0 end) as beat_close_rate,
        avg(entry_price) as mean_entry_price,
        sum(case when was_surfaced then 1 else 0 end) as n_surfaced,
        sum(case when was_suppressed then 1 else 0 end) as n_suppressed
    from scored
    group by price_bucket_cents

),

with_stderr as (

    select
        *,
        -- Standard error of the mean. CLV is continuous, so this is the
        -- t-style form rather than the binomial one used for settled outcomes.
        case
            when n > 1 and sd_clv_cents is not null
                then sd_clv_cents / sqrt(n)
        end as stderr_cents
    from by_bucket

)

select
    price_bucket_cents,
    n,
    n_surfaced,
    n_suppressed,
    round(mean_entry_price, 4) as mean_entry_price,
    round(mean_clv_cents, 3) as mean_clv_cents,
    round(stderr_cents, 3) as stderr_cents,
    round(beat_close_rate, 3) as beat_close_rate,

    -- Two independent conditions, and both must hold. Either alone is not
    -- enough: a tiny sample clears two standard errors by luck often enough
    -- to be worthless, and a large sample with a tiny effect is not a finding.
    n >= {{ var('min_scored_recommendations') }}
        and stderr_cents is not null
        and abs(mean_clv_cents) > 2 * stderr_cents
        as is_distinguishable,

    -- Same censoring as mart_calibration, for the same reason. `beat_close_rate`
    -- and `mean_clv_cents` ARE the finding here -- "did you beat the close?" --
    -- so rendering them beside a verdict of "insufficient sample: 36 of 300"
    -- shows the result while the verdict says there isn't one. The raw columns
    -- above stay available for analysis; these are what a dashboard renders.
    case
        when n < {{ var('min_scored_recommendations') }}
            or stderr_cents is null
            or abs(mean_clv_cents) <= 2 * stderr_cents
            then '(noise)'
        else printf('%.1f%%', 100 * beat_close_rate)
    end as beat_close_display,

    case
        when n < {{ var('min_scored_recommendations') }}
            or stderr_cents is null
            or abs(mean_clv_cents) <= 2 * stderr_cents
            then '(noise)'
        else printf('%+.2f', mean_clv_cents)
    end as clv_display,

    case
        when n < {{ var('min_scored_recommendations') }}
            then 'insufficient sample: ' || n || ' of '
                 || {{ var('min_scored_recommendations') }}
                 || ' — CLV needs 200-300 before it means anything'
        when stderr_cents is null
            then 'no variance estimate'
        when abs(mean_clv_cents) <= 2 * stderr_cents
            then '(noise) — within two standard errors of zero'
        when mean_clv_cents > 0
            then 'beating the close by ' || round(mean_clv_cents, 2) || 'c per bet'
        else 'losing to the close by ' || round(abs(mean_clv_cents), 2) || 'c per bet'
    end as verdict

from with_stderr
order by price_bucket_cents
