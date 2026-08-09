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

-- `union_by_name = true` is load-bearing, not tidiness. Each publish writes a
-- full snapshot into a dated partition, so the lake holds partitions written
-- before and after any schema change. Positional union makes the *first* added
-- column a hard failure of the whole warehouse -- `Binder Error: Referenced
-- column not found`, from adding a column in a different subsystem. By name,
-- an older partition simply carries NULL there, and the dedupe below keeps only
-- the newest view of each row, which has the column. Found by adding
-- `reference_contracts`; it would have broken on whatever came next regardless.
with source as (

    select *
    from read_parquet(
        '../data/lake/recommendations/**/*.parquet',
        hive_partitioning = true,
        union_by_name = true
    )

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
    -- **Net of fees already.** Do not subtract `fee_predicted` from this, and
    -- do not compare it to a fee to build a "does it clear the fee" band --
    -- that charges the fee twice. `schema.sql` described this column as gross
    -- until 2026-08-09; the code has always stored net.
    --
    -- It is also priced at ONE size, `max(1, sizing.contracts)` in `engine.py`,
    -- and the fee's per-order rounding is size-dependent. So an `avg(edge_cents)`
    -- across rows with different `suggested_contracts` averages numbers on
    -- different scales, and every row the sizer zeroed is priced at a single
    -- contract. For any other size, recompute from `entry_ask_tenths` and
    -- `fair_probability`. See the addendum to `docs/adr/0017`.
    edge_tenths,
    edge_tenths / 10.0 as edge_cents,
    fee_predicted,
    ev_net_dollars,
    kelly_fraction,
    suggested_contracts,
    -- The size at the fixed reference profile, which is what the gate counts.
    -- Carried into the warehouse so a mart can reproduce the gate's population
    -- rather than approximating it from the operator's size -- those two agree
    -- only while the deployed bankroll equals the reference one. ADR 0015.
    reference_contracts,

    kalshi_quote_age_ms,
    odds_age_ms,

    suppressed_reason,
    reason_text,
    -- **Two flags, because there are two questions.** `was_surfaced` is what
    -- the operator could have bought at the bankroll of the day; `was_actionable`
    -- is whether the strategy had a bet at all, and is the gate's population.
    -- They agree only while the deployed bankroll equals the reference one, and
    -- a mart that pooled them would read a deposit change as a strategy change.
    suppressed_reason is null and suggested_contracts > 0 as was_surfaced,
    suppressed_reason is null and reference_contracts > 0 as was_actionable,
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
