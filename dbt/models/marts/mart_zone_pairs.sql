{{ config(materialized="table") }}

select
    trips.pickup_zone_id,
    pickup.zone_name as pickup_zone,
    pickup.borough as pickup_borough,
    trips.dropoff_zone_id,
    dropoff.zone_name as dropoff_zone,
    dropoff.borough as dropoff_borough,
    count(*) as trips,
    avg(trips.fare_amount) as avg_fare,
    avg(trips.trip_duration_min) as avg_duration_min,
    avg(trips.avg_speed_mph) as avg_speed_mph,
    avg(trips.tip_pct) filter (where trips.payment_type = 1) as avg_tip_pct
from {{ ref("fct_trips") }} as trips
inner join {{ ref("dim_zone") }} as pickup
    on trips.pickup_zone_id = pickup.zone_id
inner join {{ ref("dim_zone") }} as dropoff
    on trips.dropoff_zone_id = dropoff.zone_id
group by 1, 2, 3, 4, 5, 6
having count(*) >= 30
