{{ config(materialized="table") }}

with trip_days as (
    select
        cast(trips.pickup_datetime as date) as trip_date,
        extract(hour from trips.pickup_datetime)::integer as hour_of_day,
        zones.borough as pickup_borough,
        weather.weather_bucket,
        count(*) as trips,
        count(*) filter (where trips.payment_type = 1) as credit_card_trips,
        count(trips.tip_pct) filter (where trips.payment_type = 1)
            as credit_card_tip_trips,
        sum(trips.fare_amount) as fare_total,
        sum(trips.tip_pct) filter (where trips.payment_type = 1) as tip_pct_total,
        sum(trips.avg_speed_mph) filter (where trips.avg_speed_mph is not null) as speed_total,
        count(*) filter (where trips.avg_speed_mph is not null) as speed_trips
    from {{ ref("fct_trips") }} as trips
    inner join {{ ref("dim_zone") }} as zones
        on trips.pickup_zone_id = zones.zone_id
    inner join {{ ref("dim_weather") }} as weather
        on trips.weather_hour = weather.local_hour
    group by 1, 2, 3, 4
),
bucket_summary as (
    select
        weather_bucket,
        hour_of_day,
        pickup_borough,
        sum(trips) as trips,
        count(*) as observed_days,
        sum(credit_card_trips) as credit_card_trips,
        sum(credit_card_tip_trips) as credit_card_tip_trips,
        sum(fare_total) / nullif(sum(trips), 0) as avg_fare,
        sum(tip_pct_total) / nullif(sum(credit_card_tip_trips), 0) as avg_tip_pct,
        sum(speed_total) / nullif(sum(speed_trips), 0) as avg_speed_mph,
        sum(trips)::double / nullif(count(*), 0) as avg_trips_per_day
    from trip_days
    group by 1, 2, 3
),
dry_baseline as (
    select
        hour_of_day,
        pickup_borough,
        avg(trips)::double as dry_avg_trips_per_day
    from trip_days
    where weather_bucket = 'dry'
    group by 1, 2
)
select
    buckets.weather_bucket,
    buckets.hour_of_day,
    buckets.pickup_borough,
    buckets.trips,
    buckets.observed_days,
    buckets.credit_card_trips,
    buckets.credit_card_tip_trips,
    buckets.avg_fare,
    buckets.avg_tip_pct,
    buckets.avg_speed_mph,
    buckets.avg_trips_per_day,
    baseline.dry_avg_trips_per_day,
    (
        buckets.avg_trips_per_day - baseline.dry_avg_trips_per_day
    ) / nullif(baseline.dry_avg_trips_per_day, 0) * 100 as demand_vs_dry_pct
from bucket_summary as buckets
left join dry_baseline as baseline
    on buckets.hour_of_day = baseline.hour_of_day
    and buckets.pickup_borough = baseline.pickup_borough
