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
    local_hour,
    cast(null as double) as temperature_2m,
    cast(null as double) as precipitation,
    cast(null as double) as rain,
    cast(null as double) as snowfall,
    cast(null as double) as wind_speed_10m,
    cast(null as integer) as weather_code,
    'unknown'::varchar as weather_bucket
from hours
