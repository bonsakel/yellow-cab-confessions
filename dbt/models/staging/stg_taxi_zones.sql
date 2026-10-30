{{ config(materialized="view") }}

select
    location_id::integer as zone_id,
    borough::varchar as borough,
    zone::varchar as zone_name,
    service_zone::varchar as service_zone,
    centroids.centroid_lat,
    centroids.centroid_lon,
    location_id in ({{ var("unknown_zone_ids") | join(", ") }}) as is_unknown_zone
from {{ source("raw", "taxi_zone_lookup") }}
left join {{ source("raw", "zone_centroids") }} as centroids
    on location_id = centroids.zone_id

union all

select
    -1 as zone_id,
    'Unknown'::varchar as borough,
    'Missing zone ID'::varchar as zone_name,
    'Unknown'::varchar as service_zone,
    cast(null as double) as centroid_lat,
    cast(null as double) as centroid_lon,
    true as is_unknown_zone
