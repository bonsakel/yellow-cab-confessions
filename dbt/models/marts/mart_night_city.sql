{{ config(materialized="table") }}

with configured_nights as (
    select
        cast(night_date as date) as night_date,
        night_name
    from {{ ref("featured_nights") }}
),
weather_nights as (
    select
        case
            when extract(hour from local_hour) < 6
                then cast(local_hour as date) - interval 1 day
            else cast(local_hour as date)
        end as night_date,
        sum(precipitation) as precipitation_total_mm
    from {{ ref("dim_weather") }}
    where extract(hour from local_hour) between 0 and 5
        or extract(hour from local_hour) between 18 and 23
    group by 1
),
rainiest_night as (
    select night_date, 'Rainiest night of the year'::varchar as night_name
    from weather_nights
    order by precipitation_total_mm desc nulls last, night_date
    limit 1
),
featured as (
    select night_date, night_name from configured_nights
    union all
    select night_date, night_name from rainiest_night
),
trip_flows as (
    select
        featured.night_name,
        featured.night_date,
        date_trunc('minute', trips.pickup_datetime)
            - (extract(minute from trips.pickup_datetime)::integer % 10) * interval 1 minute
            as time_bin,
        trips.pickup_zone_id,
        trips.dropoff_zone_id,
        count(*) as trips
    from featured
    inner join {{ ref("fct_trips") }} as trips
        on trips.pickup_datetime >= featured.night_date + interval 18 hour
        and trips.pickup_datetime < featured.night_date + interval 30 hour
    group by 1, 2, 3, 4, 5
)
select
    flows.night_name,
    flows.night_date,
    flows.time_bin,
    flows.pickup_zone_id,
    pickup.zone_name as pickup_zone,
    pickup.centroid_lat as pickup_lat,
    pickup.centroid_lon as pickup_lon,
    flows.dropoff_zone_id,
    dropoff.zone_name as dropoff_zone,
    dropoff.centroid_lat as dropoff_lat,
    dropoff.centroid_lon as dropoff_lon,
    flows.trips
from trip_flows as flows
inner join {{ ref("dim_zone") }} as pickup
    on flows.pickup_zone_id = pickup.zone_id
inner join {{ ref("dim_zone") }} as dropoff
    on flows.dropoff_zone_id = dropoff.zone_id
