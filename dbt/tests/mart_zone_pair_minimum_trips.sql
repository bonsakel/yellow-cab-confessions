select pickup_zone_id, dropoff_zone_id
from {{ ref("mart_zone_pairs") }}
where trips < 30
