-- One row per claim, assigning a handler from that claim's own rating
-- group (Claims Handler role only - Reserving Actuary and Senior
-- Management are oversight roles for row-level security, not caseworkers,
-- so they never own an individual claim).
--
-- Assignment is a deterministic hash of claim_id modulo the number of
-- handlers in that group, not a random draw, so re-running this model
-- always assigns the same claim to the same handler rather than
-- reshuffling on every dbt run.
--
-- Claims left "Unclassified" (missing rating_group, see
-- int_claims_header_clean) get no handler_id, same reasoning as
-- everywhere else they're excluded: guessing an owner for a claim whose
-- own group is unknown would manufacture a fact that isn't there.
with handlers as (
    select handler_id, assigned_rating_group
    from {{ ref('dim_claims_handler') }}
    where role = 'Claims Handler'
),

handler_pools as (
    select
        assigned_rating_group,
        count(*) as handler_count,
        array_agg(handler_id order by handler_id) as handler_ids
    from handlers
    group by assigned_rating_group
),

claims as (
    select claim_id, rating_group
    from {{ ref('int_claims_header_clean') }}
)

select
    c.claim_id,
    p.handler_ids[(abs(hashtext(c.claim_id)) % p.handler_count) + 1] as handler_id
from claims c
join handler_pools p on c.rating_group = p.assigned_rating_group
