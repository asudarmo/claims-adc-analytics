-- Singular test: at most one reserving run may be promoted at a time.
-- "At most", not "exactly", since a fresh database with no promotion yet
-- is a legitimate state, not a failure. A dbt test passes when it returns
-- zero rows, so this only surfaces a row when the invariant is broken.
select count(*) as promoted_count
from {{ source('reserving_engine', 'dim_reserving_run') }}
where is_promoted
having count(*) > 1
