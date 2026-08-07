-- Every candidate the engine judged, surfaced or not.
--
-- Suppressed rows are kept deliberately. They carry a price and a fair
-- estimate, so they are scored on closing-line value exactly like surfaced
-- ones -- which is what makes 300 scored observations reachable without 300
-- wagers, and what makes each suppression rule auditable rather than an
-- article of faith.
--
-- Prices arrive as integer tenths of a cent and are converted to probabilities
-- here, once, at the edge of the warehouse. Doing it in each mart would mean
-- the conversion existing in five places, which is five places for it to drift.

with source as (

    select *
    from read_parquet('../data/lake/recommendations/**/*.parquet', hive_partitioning = true)

),

deduplicated as (

    -- Each publish writes a full snapshot, so a row appears once per partition
    -- it survived into. Keep only the most recent view of each recommendation.
    select
        *,
        row_number() over (partition by id order by published_ms desc) as _recency
    from source

)

select
    id as recommendation_id,
    created_ms,
    to_timestamp(created_ms / 1000) as created_at,
    strategy_config_version,
    ticker,
    link_id,
    side,

    -- The price ACTUALLY PAID. Never a mid. One bucket in the predecessor
    -- project showed a +25.4-point edge while losing $4.92 a market because it
    -- was bucketed on the mid and transacted at the ask.
    entry_ask_tenths,
    entry_ask_tenths / 1000.0 as entry_price,
    depth_at_ask,

    fair_probability,
    model_probability,
    edge_tenths,
    edge_tenths / 10.0 as edge_cents,
    fee_predicted,
    ev_net_dollars,
    kelly_fraction,
    suggested_contracts,

    kalshi_quote_age_ms,
    odds_age_ms,

    suppressed_reason,
    reason_text,
    suppressed_reason is null and suggested_contracts > 0 as was_surfaced,
    suppressed_reason is not null as was_suppressed,

    clv_tenths,
    clv_tenths / 10.0 as clv_cents,
    clv_scored_ms is not null as is_scored,

    -- Bucket on the price paid, in 10c bands. This is the axis every
    -- measurement below groups by.
    -- `//`, not `/`. DuckDB's `/` returns DOUBLE even on integers, so
    -- `(485 / 100) * 10` is 48.5 -- the price in cents at full deci-cent
    -- resolution, not a 10c band. That silently turned 10 buckets into up to
    -- 990, each with ~1/100th the sample, which (a) makes the n >= 300 guard in
    -- mart_clv_by_bucket structurally unreachable, (b) multiplies the number of
    -- tests being run without the multiple-comparisons mart knowing, and
    -- (c) disagrees with analysis/validate.py, which does band correctly.
    -- The `73.0` bucket recorded in tasks/lessons.md is this bug's fingerprint.
    (entry_ask_tenths // 100) * 10 as price_bucket_cents

from deduplicated
where _recency = 1
