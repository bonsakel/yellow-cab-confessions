select airport, direction, day_type, hour_of_day, other_end_borough
from {{ ref("mart_airport_runs") }}
where duration_p10_min > duration_p50_min
    or duration_p50_min > duration_p90_min
    or fare_p10 > fare_p50
    or fare_p50 > fare_p90
