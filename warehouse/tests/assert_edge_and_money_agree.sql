-- Fails the build when a measured edge and realised money disagree in sign by
-- more than any fee can explain.
--
-- The entry fee peaks at 1.75c/contract, so a small positive edge with negative
-- money is fees working correctly. Above the tolerance nothing explains it,
-- which means the bucketing has drifted off the transaction price -- almost
-- certainly onto the mid.
--
-- This is a genuine stop-the-line: a measurement keyed on the wrong price
-- makes every downstream number wrong in the flattering direction.

select
    price_bucket_cents,
    n,
    gap_points,
    mean_pnl_cents,
    'edge ' || round(gap_points, 1) || ' points but P&L '
        || round(mean_pnl_cents, 2) || 'c — check the bucket is keyed on the '
        || 'price actually paid, not the mid' as violation
from {{ ref('mart_calibration') }}
where edge_money_disagree
