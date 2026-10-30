select pickup_zone_id, dropoff_zone_id
from {{ ref("mart_zone_pairs") }}
group by 1, 2
having count(*) > 1
