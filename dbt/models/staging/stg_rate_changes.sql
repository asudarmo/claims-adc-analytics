select
    accident_year::int as accident_year,
    rating_group,
    rate_change
from {{ source('raw', 'rate_changes') }}
