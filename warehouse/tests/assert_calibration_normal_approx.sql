-- No calibration cell may claim significance where the normal approximation
-- does not apply.
--
-- The predecessor project produced a 74-point "finding" from a two-market cell
-- that passed a significance test. The arithmetic was fine; the assumption
-- behind it was not. This test makes that assumption load-bearing.

select
    price_bucket_cents,
    n,
    implied_probability,
    gap_points,
    'significant despite n*p or n*(1-p) below '
        || {{ var('min_expected_per_side') }} as violation
from {{ ref('mart_calibration') }}
where is_distinguishable
  and not normal_approx_valid
