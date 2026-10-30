{{ config(materialized="table") }}

with year_bounds as (
    select
        timestamp '{{ var("ycc_year") }}-01-01 00:00:00' as year_start,
        timestamp '{{ var("ycc_year") + 1 }}-01-01 00:00:00' as year_end
),
hours as (
    select
        year_start + hour_offset * interval 1 hour as local_hour
    from year_bounds,
        range(0, date_diff('hour', year_start, year_end)) as generated(hour_offset)
)
select
    hours.local_hour,
    weather.temperature_2m,
    weather.precipitation,
    weather.rain,
    weather.snowfall,
    weather.wind_speed_10m,
    weather.weather_code,
    case
        when weather.local_hour is null then 'unknown'
        when weather.snowfall > 0 then 'snow'
        when weather.precipitation is null then 'unknown'
        when weather.precipitation < {{ var("weather_dry_threshold_mm") }} then 'dry'
        when weather.precipitation < {{ var("weather_light_rain_upper_mm") }} then 'light_rain'
        when weather.precipitation <= {{ var("weather_moderate_rain_upper_mm") }}
            then 'moderate_rain'
        else 'heavy_rain'
    end as weather_bucket
from hours
left join {{ ref("stg_weather_hourly") }} as weather
    on hours.local_hour = weather.local_hour
