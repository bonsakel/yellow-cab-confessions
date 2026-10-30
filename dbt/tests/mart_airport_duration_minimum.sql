select airport, direction, day_type, hour_of_day, other_end_borough
from {{ ref("mart_airport_runs") }}
where duration_p10_min < {{ var("airport_min_duration_minutes") }}
