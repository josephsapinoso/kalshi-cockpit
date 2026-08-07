-- A cell that cannot support a finding must render `(noise)` in EVERY column
-- that carries a result -- not just in the one that names the conclusion.
--
-- This is not cosmetic. A number in such a cell gets read as a result no matter
-- what caveat sits beside it: that is how a bucket showing +25.4 points while
-- losing $4.92 a market got treated as a finding.
--
-- Two things this test learned the hard way.
--
-- **It used to be a tautology.** The predicate was
-- `not is_distinguishable and gap_display != '(noise)'`, and since
-- `is_distinguishable` is *defined* as `normal_approx_valid and abs(gap) >
-- 2*stderr` while `gap_display` is `(noise)` under exactly the negation of
-- that, the whole thing reduced to `(A and B) and not (A and B)` -- identically
-- false, and green against any bug. It now recomputes the condition from the
-- raw columns (`n`, `implied_probability`, `gap_points`, `stderr_points`), so
-- it is comparing two independent derivations rather than one against itself.
--
-- **Suppressing the conclusion is not suppressing the finding.** `gap` is
-- `actual - implied`, so a row rendering both operands beside a `(noise)` gap
-- hands the reader the result to reconstruct by subtraction. `actual_display`
-- and `pnl_display` are therefore checked too. `implied_probability` is
-- deliberately NOT censored -- it is the price paid, a known input rather than
-- an outcome, and withholding one operand is enough to break the subtraction.

with recomputed as (

    select
        price_bucket_cents,
        n,
        gap_points,
        stderr_points,
        gap_display,
        actual_display,
        pnl_display,

        -- Independent of `is_distinguishable`: built from the inputs, not from
        -- the flag this test exists to check.
        n * implied_probability >= {{ var('min_expected_per_side') }}
            and n * (1 - implied_probability) >= {{ var('min_expected_per_side') }}
            and abs(gap_points) > 2 * stderr_points
            as should_speak

    from {{ ref('mart_calibration') }}

)

select
    price_bucket_cents,
    n,
    gap_points,
    stderr_points,
    should_speak,
    gap_display,
    actual_display,
    pnl_display,
    case
        when not should_speak and gap_display != '(noise)'
            then 'indistinguishable cell rendered a gap'
        when not should_speak and actual_display != '(noise)'
            then 'indistinguishable cell rendered its outcome rate -- the gap '
                 || 'is recoverable by subtracting the implied column'
        when not should_speak and pnl_display != '(noise)'
            then 'indistinguishable cell rendered a P&L'
        else 'a cell that should speak was silenced'
    end as violation

from recomputed
where (not should_speak and (
          gap_display != '(noise)'
          or actual_display != '(noise)'
          or pnl_display != '(noise)'
      ))
   -- The other direction matters too: a guard that silences everything is not
   -- a guard, it is a broken dashboard.
   or (should_speak and gap_display = '(noise)')
