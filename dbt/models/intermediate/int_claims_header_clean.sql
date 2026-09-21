-- Cleans stg_claims_header per the rules in docs/SCHEMA_DESIGN.md:
--   - missing rating_group is NOT guessed - relabelled 'Unclassified' and
--     flagged, so it can be excluded from group-level triangles with the
--     excluded volume disclosed rather than silently absorbed into a group
--     it wasn't shown to belong to.
--   - missing report_date IS imputed, from that rating group's own median
--     reporting lag (falling back to the portfolio-wide median on the rare
--     row missing both fields at once).
with headers as (
    select * from {{ ref('stg_claims_header') }}
),

group_lag as (
    select
        rating_group,
        percentile_cont(0.5) within group (order by (report_date - accident_date)) as median_lag_days
    from headers
    where rating_group is not null and report_date is not null
    group by rating_group
),

portfolio_lag as (
    select percentile_cont(0.5) within group (order by (report_date - accident_date)) as median_lag_days
    from headers
    where report_date is not null
)

select
    h.claim_id,
    coalesce(h.rating_group, 'Unclassified') as rating_group,
    (h.rating_group is null) as rating_group_was_missing,
    h.accident_year,
    h.accident_date,
    coalesce(
        h.report_date,
        h.accident_date + round(coalesce(gl.median_lag_days, pl.median_lag_days))::int
    ) as report_date,
    (h.report_date is null) as report_date_was_imputed,
    h.close_date,
    h.status
from headers h
left join group_lag gl on h.rating_group = gl.rating_group
cross join portfolio_lag pl
