{{ config(materialized="table") }}

select
    trips.trip_id,
    cast(strftime(trips.trip_date, '%Y%m%d') as integer) as date_key,
    trips.pickup_local_hour as weather_hour,
    coalesce(trips.pickup_location_id, -1) as pickup_zone_id,
    coalesce(trips.dropoff_location_id, -1) as dropoff_zone_id,
    payment.payment_key,
    trips.source_file,
    trips.vendor_id,
    trips.payment_type,
    trips.rate_code_id,
    trips.pickup_datetime,
    trips.dropoff_datetime,
    trips.pickup_local_hour,
    trips.trip_distance,
    trips.trip_duration_min,
    trips.avg_speed_mph,
    trips.passenger_count,
    trips.fare_amount,
    trips.tip_amount,
    trips.tolls_amount,
    trips.total_amount,
    trips.congestion_surcharge,
    trips.airport_fee,
    trips.cbd_congestion_fee,
    case
        when trips.payment_type = 1
            then trips.tip_amount / nullif(trips.fare_amount, 0) * 100
        else null
    end as tip_pct,
    (
        trips.pickup_location_id in (1, 132, 138)
        or trips.dropoff_location_id in (1, 132, 138)
    ) as is_airport_trip,
    trips.is_unknown_zone
from {{ ref("stg_yellow_trips") }} as trips
inner join {{ ref("dim_payment") }} as payment
    on trips.payment_type is not distinct from payment.payment_type
    and trips.rate_code_id is not distinct from payment.rate_code_id
inner join {{ ref("dim_zone") }} as pickup_zone
    on coalesce(trips.pickup_location_id, -1) = pickup_zone.zone_id
inner join {{ ref("dim_zone") }} as dropoff_zone
    on coalesce(trips.dropoff_location_id, -1) = dropoff_zone.zone_id
inner join {{ ref("dim_date") }} as dates
    on trips.trip_date = dates.date_day
inner join {{ ref("dim_weather") }} as weather
    on trips.pickup_local_hour = weather.local_hour
where list_count(trips.reject_reasons) = 0
