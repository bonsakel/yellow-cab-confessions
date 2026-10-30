{{ config(materialized="table") }}

select
    trip_id,
    source_file,
    source_month,
    pickup_datetime,
    dropoff_datetime,
    pickup_location_id,
    dropoff_location_id,
    fare_amount,
    total_amount,
    trip_distance,
    trip_duration_min,
    avg_speed_mph,
    reject_reasons,
    list_count(reject_reasons) as rejection_count,
    is_unknown_zone
from {{ ref("stg_yellow_trips") }}
where list_count(reject_reasons) > 0
