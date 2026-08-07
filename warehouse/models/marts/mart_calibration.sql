-- Calibration: did things priced at X% happen X% of the time?
--
-- This is the honest chart. A model can have a good win rate and be badly
-- calibrated, and a badly calibrated model produces sizing that is wrong in a
-- direction you cannot see from P&L alone.
--
-- The noise guard here is the *binomial* form, and the standard error is
-- computed **under the null** -- at the implied rate, not the observed one.
-- Using the observed rate makes an extreme result look more certain precisely
-- because it is extreme, which is the failure mode that let a two-market cell
-- produce a 74-point "finding".

with settled as (

    select
        r.price_bucket_cents,
        r.entry_price,
        r.side,
        s.result,
        s.pnl_cents,
        case when s.result = r.side then 1 else 0 end as won
    from {{ ref('stg_recommendations') }} r
    join read_parquet('../data/lake/settlements/**/*.parquet', hive_partitioning = true) s
      on s.ticker = r.ticker

),

by_bucket as (

    select
        price_bucket_cents,
        count(*) as n,
        avg(entry_price) as implied_probability,
        avg(won::double) as actual_rate,
        avg(pnl_cents) as mean_pnl_cents
    from settled
    group by price_bucket_cents

),

guarded as (

    select
        *,
        (actual_rate - implied_probability) * 100 as gap_points,

        -- Under the null: p is the implied rate.
        100.0 * sqrt(
            greatest(implied_probability, 1e-9)
            * greatest(1 - implied_probability, 1e-9)
            / n
        ) as stderr_points,

        -- Normal approximation is only valid with enough expected outcomes on
        -- BOTH sides. Arithmetic below this still produces a number; the
        -- number is meaningless.
        n * implied_probability >= {{ var('min_expected_per_side') }}
            and n * (1 - implied_probability) >= {{ var('min_expected_per_side') }}
            as normal_approx_valid
    from by_bucket

)

select
    price_bucket_cents,
    n,
    round(implied_probability, 4) as implied_probability,
    round(actual_rate, 4) as actual_rate,
    round(gap_points, 2) as gap_points,
    round(stderr_points, 2) as stderr_points,
    round(mean_pnl_cents, 3) as mean_pnl_cents,
    normal_approx_valid,

    normal_approx_valid and abs(gap_points) > 2 * stderr_points as is_distinguishable,

    -- The rendered cells. `(noise)` rather than a number, because a number here
    -- gets read as a result no matter what caveat sits beside it.
    --
    -- **Three columns, not one, and that is the point.** Suppressing only
    -- `gap_display` did not suppress the gap: `gap = actual - implied`, so a
    -- dashboard rendering both operands beside a `(noise)` cell hands the
    -- reader the finding to reconstruct by subtraction. The seeded demo showed
    -- exactly that -- `73.0c | 46 | 73.0% | 52.2% | (noise)` -- from which
    -- anyone recovers the 20.8-point "finding" the guard exists to withhold.
    --
    -- `actual_rate` is censored and `implied_probability` is not, because they
    -- are different kinds of number. Implied is the price paid: a known input,
    -- true whatever happens next. Actual is the outcome, and the outcome minus
    -- the price IS the claim. Withholding either operand breaks the
    -- subtraction; withholding the one that is a result is the honest half.
    --
    -- `mean_pnl_cents` is censored for the reason CLAUDE.md gives directly:
    -- printing a P&L in a cell that cannot support a finding invites reading
    -- it as one.
    case
        when not normal_approx_valid then '(noise)'
        when abs(gap_points) <= 2 * stderr_points then '(noise)'
        else printf('%+.1f', gap_points)
    end as gap_display,

    case
        when not normal_approx_valid then '(noise)'
        when abs(gap_points) <= 2 * stderr_points then '(noise)'
        else printf('%.1f%%', 100 * actual_rate)
    end as actual_display,

    case
        when not normal_approx_valid then '(noise)'
        when abs(gap_points) <= 2 * stderr_points then '(noise)'
        else printf('%+.2f', mean_pnl_cents)
    end as pnl_display,

    -- Guard 3: edge and money must agree in sign. Below the tolerance, fees
    -- explain the disagreement -- the entry fee peaks at 1.75c/contract. Above
    -- it, nothing does, which means the bucketing has drifted off the
    -- transaction price again.
    normal_approx_valid
        and abs(gap_points) > 2 * stderr_points
        and gap_points > {{ var('edge_money_tolerance_cents') }}
        and mean_pnl_cents < 0
        as edge_money_disagree

from guarded
order by price_bucket_cents
