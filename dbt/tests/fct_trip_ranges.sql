select trip_id
from {{ ref("fct_trips") }}
where fare_amount < 0
    or total_amount <= 0
    or trip_distance > {{ var("absurd_distance_miles") }}
    or trip_duration_min < 0
    or trip_duration_min > {{ var("absurd_duration_minutes") }}
    or avg_speed_mph > {{ var("teleporting_speed_mph") }}
