-- Is each suppression rule earning its place?
--
-- Suppression rules are not free. Every one refuses bets, and a miscalibrated
-- rule refuses *good* bets silently -- there is no error, just an opportunity
-- that never appeared. The only way to know is to score the rejects and look.
--
-- That is why the engine stores suppressed rows and scores them on CLV exactly
-- like surfaced ones. This mart is the payoff: if rows rejected for
-- `wide_market` turn out to have had strong CLV, that rule is costing money and
-- the number says so.
--
-- Reading it: `mean_clv_cents` well above zero on a rule with a real sample is
-- evidence the rule is too tight. Near zero or negative is the rule working.
--
-- "A real sample" is the same floor every other mart holds:
-- `min_scored_recommendations`. It was hardcoded at 30 here until 2026-08-29,
-- so this mart judged rules on samples its siblings refused to speak about.
-- ADR 0065 §3's `n >= 30` is a *display* floor, never a verdict floor: at
-- n = 30 the design resolves only a 26-63-point calibration bias (2026-08-29
-- registration §6a), an instrument that can tell "betting the wrong side"
-- from nothing and no more. Below the floor the numbers still render, and the
-- verdict column states the sample and stops.

with scored as (

    select *
    from {{ ref('stg_recommendations') }}
    where is_scored

),

-- A row can fail several checks at once, so `suppressed_reason` is a
-- comma-joined list. Split it: a rule's record should count every row it
-- rejected, not only those it rejected alone.
exploded as (

    select
        unnest(string_split(suppressed_reason, ',')) as rule_name,
        clv_cents,
        edge_cents,
        entry_price
    from scored
    where was_suppressed

),

per_rule as (

    select
        rule_name,
        count(*) as n_rejected,
        avg(clv_cents) as mean_clv_cents,
        stddev_samp(clv_cents) as sd_clv_cents,
        avg(edge_cents) as mean_claimed_edge_cents,
        avg(entry_price) as mean_entry_price
    from exploded
    group by rule_name

),

surfaced_baseline as (

    select avg(clv_cents) as baseline_clv_cents
    from scored
    where was_surfaced

)

select
    r.rule_name,
    r.n_rejected,
    round(r.mean_clv_cents, 3) as mean_clv_cents,
    round(b.baseline_clv_cents, 3) as surfaced_clv_cents,
    round(r.mean_claimed_edge_cents, 2) as mean_claimed_edge_cents,
    round(r.mean_entry_price, 4) as mean_entry_price,

    case
        when r.n_rejected > 1 and r.sd_clv_cents is not null
            then round(r.sd_clv_cents / sqrt(r.n_rejected), 3)
    end as stderr_cents,

    case
        when r.n_rejected < {{ var('min_scored_recommendations') }}
            then 'insufficient sample: ' || r.n_rejected || ' of '
                 || {{ var('min_scored_recommendations') }}
                 || ' — displayed, not judged'
        when r.sd_clv_cents is null
            then 'no variance estimate'
        when r.mean_clv_cents > 2 * (r.sd_clv_cents / sqrt(r.n_rejected))
            then 'REVIEW: rejected bets had positive CLV — this rule may be too tight'
        when abs(r.mean_clv_cents) <= 2 * (r.sd_clv_cents / sqrt(r.n_rejected))
            then 'rule looks neutral — rejected bets show no demonstrated edge'
        else 'rule looks protective — rejected bets underperformed the close'
    end as verdict

from per_rule r
cross join surfaced_baseline b
order by r.n_rejected desc
