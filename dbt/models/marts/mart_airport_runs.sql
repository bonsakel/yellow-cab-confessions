{{ config(materialized="table") }}

with airport_directions as (
    select
        trips.trip_id,
        case trips.dropoff_zone_id
            when 132 then 'JFK'
            when 138 then 'LGA'
            when 1 then 'EWR'
        end as airport,
        'to_airport'::varchar as direction,
        pickup_zone.borough as other_end_borough,
        trips.pickup_local_hour as local_hour,
        dates.is_weekend,
        dates.holiday_name,
        trips.trip_duration_min,
        trips.fare_amount
    from {{ ref("fct_trips") }} as trips
    inner join {{ ref("dim_zone") }} as pickup_zone
        on trips.pickup_zone_id = pickup_zone.zone_id
    inner join {{ ref("dim_date") }} as dates
        on trips.date_key = dates.date_key
    where trips.dropoff_zone_id in (1, 132, 138)
        and trips.trip_duration_min >= {{ var("airport_min_duration_minutes") }}

    union all

    select
        trips.trip_id,
        case trips.pickup_zone_id
            when 132 then 'JFK'
            when 138 then 'LGA'
            when 1 then 'EWR'
        end as airport,
        'from_airport'::varchar as direction,
        dropoff_zone.borough as other_end_borough,
        trips.pickup_local_hour as local_hour,
        dates.is_weekend,
        dates.holiday_name,
        trips.trip_duration_min,
        trips.fare_amount
    from {{ ref("fct_trips") }} as trips
    inner join {{ ref("dim_zone") }} as dropoff_zone
        on trips.dropoff_zone_id = dropoff_zone.zone_id
    inner join {{ ref("dim_date") }} as dates
        on trips.date_key = dates.date_key
    where trips.pickup_zone_id in (1, 132, 138)
        and trips.trip_duration_min >= {{ var("airport_min_duration_minutes") }}
),
classified as (
    select
        *,
        extract(hour from local_hour)::integer as hour_of_day,
        case
            when holiday_name is not null then 'holiday'
            when is_weekend then 'weekend'
            else 'weekday'
        end as day_type
    from airport_directions
)
select
    airport,
    direction,
    day_type,
    hour_of_day,
    other_end_borough,
    count(*) as trips,
    quantile_cont(trip_duration_min, 0.1) as duration_p10_min,
    quantile_cont(trip_duration_min, 0.5) as duration_p50_min,
    quantile_cont(trip_duration_min, 0.9) as duration_p90_min,
    quantile_cont(fare_amount, 0.1) as fare_p10,
    quantile_cont(fare_amount, 0.5) as fare_p50,
    quantile_cont(fare_amount, 0.9) as fare_p90
from classified
group by 1, 2, 3, 4, 5
