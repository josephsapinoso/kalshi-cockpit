-- A bucket may not be marked distinguishable without clearing BOTH conditions.
--
-- This is the noise guard expressed as a build failure rather than as a
-- docstring. If someone later loosens the logic in `mart_clv_by_bucket` --
-- because the board looks empty and a finding would be nice -- `dbt build`
-- goes red instead of the dashboard quietly gaining a number.
--
-- A test returning rows is a failure in dbt.

select
    price_bucket_cents,
    n,
    mean_clv_cents,
    stderr_cents,
    'marked distinguishable on ' || n || ' observations' as violation
from {{ ref('mart_clv_by_bucket') }}
where is_distinguishable
  and (
        n < {{ var('min_scored_recommendations') }}
     or stderr_cents is null
     or abs(mean_clv_cents) <= 2 * stderr_cents
  )
