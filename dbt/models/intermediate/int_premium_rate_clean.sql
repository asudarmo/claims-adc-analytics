-- earned_premium and rate_changes joined, validated, and corrected by a
-- stated rule (not silently interpolated without disclosure):
--   - rate_change outside +/-25% (same bound as the original workbook's
--     Val_rate_min/Val_rate_max) is treated as a magnitude keying error and
--     divided by 100 - the exact inverse of how the seeded error was made,
--     stated here as the documented correction rule, same spirit as the
--     original model's "state and quantify the correction" requirement.
--   - a missing premium cell is filled by the average of the adjacent
--     accident years for the same rating group (simple linear interpolation).
-- Both corrections are flagged so a consumer can tell a real value from a
-- corrected one.
with premium as (
    select * from {{ ref('stg_earned_premium') }}
),

rates as (
    select * from {{ ref('stg_rate_changes') }}
),

joined as (
    select
        coalesce(p.accident_year, r.accident_year) as accident_year,
        coalesce(p.rating_group, r.rating_group) as rating_group,
        p.earned_premium_000,
        r.rate_change
    from premium p
    full outer join rates r
        on p.accident_year = r.accident_year and p.rating_group = r.rating_group
),

premium_interpolated as (
    select
        *,
        (
            lag(earned_premium_000) over (partition by rating_group order by accident_year)
            + lead(earned_premium_000) over (partition by rating_group order by accident_year)
        ) / 2.0 as earned_premium_000_neighbour_avg
    from joined
)

select
    accident_year,
    rating_group,
    coalesce(earned_premium_000, earned_premium_000_neighbour_avg) as earned_premium_000,
    (earned_premium_000 is null) as earned_premium_was_missing,
    case when rate_change between -0.25 and 0.25 then rate_change else rate_change / 100 end as rate_change,
    (rate_change is not null and rate_change not between -0.25 and 0.25) as rate_change_was_corrected
from premium_interpolated
