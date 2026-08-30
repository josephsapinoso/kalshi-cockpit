-- The suppression audit may not judge a rule below the shared verdict floor.
--
-- `mart_suppression_audit`'s `verdict` column pronounces on a rule -- too
-- tight, neutral, protective -- and until 2026-08-29 it did so from
-- `n_rejected >= 30` while every sibling mart held verdicts to
-- `min_scored_recommendations` (300) on the same kind of column. ADR 0065
-- §3's `n >= 30` is a *display* floor: at n = 30 the design resolves only a
-- 26-63-point calibration bias (2026-08-29 registration §6a), which is not a
-- verdict-grade instrument. Below the floor the verdict column may state the
-- sample and nothing else.
--
-- A test returning rows is a failure in dbt.
--
-- What this does not establish: that the demo lake exercises it. Demo data
-- carries no scored rows, so this mart is empty there and this test is
-- vacuously green in CI. It bites on a lake with scored suppressions -- the
-- live one, the moment a session runs `dbt build` locally.

select
    rule_name,
    n_rejected,
    verdict,
    'a rule was judged on ' || n_rejected || ' rejections' as violation
from {{ ref('mart_suppression_audit') }}
where n_rejected < {{ var('min_scored_recommendations') }}
  and verdict not like 'insufficient sample%'
