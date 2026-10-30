{{ config(materialized="view") }}

select
    cast(local_hour as timestamp) as local_hour,
    try_cast(temperature_2m as double) as temperature_2m,
    try_cast(precipitation as double) as precipitation,
    try_cast(rain as double) as rain,
    try_cast(snowfall as double) as snowfall,
    try_cast(wind_speed_10m as double) as wind_speed_10m,
    try_cast(weather_code as integer) as weather_code
from {{ source("raw", "weather_hourly") }}
