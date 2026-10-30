{{ config(materialized="table") }}

with expanded as (
    select
        trips.trip_id,
        trips.source_file,
        trips.source_month,
        reasons.reason_code,
        trips.pickup_datetime,
        trips.dropoff_datetime,
        trips.pickup_location_id,
        trips.dropoff_location_id,
        trips.passenger_count,
        trips.trip_distance,
        trips.fare_amount,
        trips.total_amount,
        trips.trip_duration_min,
        trips.avg_speed_mph,
        trips.reject_reasons,
        case reasons.reason_code
            when 'NEGATIVE_FARE' then abs(least(trips.fare_amount, trips.total_amount))
            when 'DROPOFF_BEFORE_PICKUP' then abs(trips.trip_duration_min)
            when 'ZERO_DURATION' then trips.trip_distance
            when 'ABSURD_DURATION' then trips.trip_duration_min
            when 'ZERO_DISTANCE_PAID' then trips.fare_amount
            when 'ABSURD_DISTANCE' then trips.trip_distance
            when 'TELEPORTING_CAB' then trips.avg_speed_mph
            when 'OUT_OF_RANGE_DATE' then 1
            when 'BAD_PASSENGER_COUNT' then trips.passenger_count
            when 'UNKNOWN_ZONE' then 1
            when 'DUPLICATE_TRIP' then trips.duplicate_rank
            else 0
        end as weirdness_score
    from {{ ref("stg_yellow_trips") }} as trips,
        unnest(trips.reject_reasons) as reasons(reason_code)
),
ranked as (
    select
        *,
        row_number() over (
            partition by reason_code
            order by weirdness_score desc nulls last, trip_id
        ) as example_rank
    from expanded
)
select
    trip_id,
    source_file,
    source_month,
    reason_code,
    pickup_datetime,
    dropoff_datetime,
    pickup_location_id,
    dropoff_location_id,
    passenger_count,
    trip_distance,
    fare_amount,
    total_amount,
    trip_duration_min,
    avg_speed_mph,
    reject_reasons,
    weirdness_score,
    example_rank
from ranked
where example_rank <= {{ var("blooper_examples_per_rule") }}
