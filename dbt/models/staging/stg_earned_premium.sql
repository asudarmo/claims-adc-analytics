select
    accident_year::int as accident_year,
    rating_group,
    earned_premium_000
from {{ source('raw', 'earned_premium') }}
