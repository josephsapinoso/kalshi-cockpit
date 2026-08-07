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
        when r.n_rejected < 30
            then 'too few rejections to judge (' || r.n_rejected || ')'
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
