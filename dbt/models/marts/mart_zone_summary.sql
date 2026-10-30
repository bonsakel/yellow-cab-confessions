{{ config(materialized="table") }}

with endpoints as (
    select
        pickup_zone_id as zone_id,
        true as is_pickup,
        fare_amount,
        avg_speed_mph,
        tip_pct,
        payment_type
    from {{ ref("fct_trips") }}

    union all

    select
        dropoff_zone_id as zone_id,
        false as is_pickup,
        fare_amount,
        avg_speed_mph,
        tip_pct,
        payment_type
    from {{ ref("fct_trips") }}
),
aggregated as (
    select
        zone_id,
        count(*) as endpoint_trips,
        count(*) filter (where is_pickup) as pickup_trips,
        count(*) filter (where not is_pickup) as dropoff_trips,
        avg(fare_amount) as avg_fare,
        avg(avg_speed_mph) as avg_speed_mph,
        avg(tip_pct) filter (where payment_type = 1) as avg_tip_pct
    from endpoints
    group by zone_id
)
select
    aggregated.zone_id,
    zones.zone_name,
    zones.borough,
    zones.centroid_lat,
    zones.centroid_lon,
    aggregated.endpoint_trips,
    aggregated.pickup_trips,
    aggregated.dropoff_trips,
    aggregated.avg_fare,
    aggregated.avg_speed_mph,
    aggregated.avg_tip_pct
from aggregated
inner join {{ ref("dim_zone") }} as zones
    on aggregated.zone_id = zones.zone_id
