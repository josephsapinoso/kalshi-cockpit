-- Predicted fee versus what Kalshi actually charged.
--
-- This mart exists to close a year-old open question. Kalshi's official fee
-- schedule returns HTTP 429 to automated fetches, and the secondary sources
-- disagree with each other: one reports a single 0.07 coefficient rounded up
-- per ORDER, another a ~0.06 sports multiplier rounded to the nearest cent per
-- CONTRACT. At 50c on 100 contracts they differ by 14%, and the ordering
-- reverses at 20c.
--
-- `core/fees.py` therefore charges the MOST EXPENSIVE candidate, which is safe
-- but costly -- under the per-contract model, sports fees are a flat
-- 1c/contract from roughly 9c to 91c, which is 10% of stake at 10c and
-- suppresses essentially every longshot.
--
-- Every fill carries ground truth. Once enough fills exist, this mart says
-- which model is real and the hedge can be retired.

with fills as (

    select *
    from read_parquet('../data/lake/fills/**/*.parquet', hive_partitioning = true, union_by_name = true)
    where fee_actual is not null

),

per_fill as (

    select
        ticker,
        filled_ms,
        count as contracts,
        price_tenths,
        price_tenths / 10.0 as price_cents,
        -- Integer division. See stg_recommendations for why `/` is wrong here.
        (price_tenths // 100) * 10 as price_bucket_cents,
        is_taker,
        fee_predicted,
        fee_actual,
        fee_actual - fee_predicted as delta,
        fee_actual / nullif(count, 0) * 100 as actual_cents_per_contract
    from fills

)

select
    price_bucket_cents,
    count(*) as n_fills,
    sum(contracts) as total_contracts,
    round(avg(fee_predicted), 4) as mean_predicted,
    round(avg(fee_actual), 4) as mean_actual,
    round(avg(delta), 4) as mean_delta,
    round(avg(actual_cents_per_contract), 3) as actual_cents_per_contract,

    -- Float noise only, matching `core.fees.FEE_MATCH_TOLERANCE_DOLLARS`.
    -- This was 0.005 -- half a cent, absolute -- which on a one-contract
    -- fill let a model be 50% wrong and still reconcile. The tolerance was
    -- larger than the quantity it was checking.
    sum(case when abs(delta) > 1e-9 then 1 else 0 end) as n_mismatched,

    -- The whole point. Any mismatch means every EV figure in the system is
    -- wrong by an unknown amount, so this is stop-the-line rather than a
    -- metric to watch.
    case
        when count(*) = 0
            then 'no fills yet — the fee model is still an unresolved hedge'
        when sum(case when abs(delta) > 1e-9 then 1 else 0 end) = 0
            then 'model matches Kalshi on ' || count(*) || ' fills'
        else 'MISMATCH on '
             || sum(case when abs(delta) > 1e-9 then 1 else 0 end)
             || ' of ' || count(*)
             || ' fills — STOP. Every EV figure is wrong until fees.py is fixed.'
    end as verdict

from per_fill
group by price_bucket_cents
order by price_bucket_cents
