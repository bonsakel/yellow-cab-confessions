{{ config(materialized="table") }}

select
    zone_id,
    borough,
    zone_name,
    service_zone,
    centroid_lat,
    centroid_lon,
    is_unknown_zone
from {{ ref("stg_taxi_zones") }}
