{{ config(materialized="view") }}

with raw_trips as (
    select
        vendor_id::integer as vendor_id,
        pickup_datetime::timestamp as pickup_datetime,
        dropoff_datetime::timestamp as dropoff_datetime,
        passenger_count::integer as passenger_count,
        trip_distance::double as trip_distance,
        rate_code_id::integer as rate_code_id,
        store_and_fwd_flag::varchar as store_and_fwd_flag,
        pickup_location_id::integer as pickup_location_id,
        dropoff_location_id::integer as dropoff_location_id,
        payment_type::integer as payment_type,
        fare_amount::double as fare_amount,
        extra::double as extra,
        mta_tax::double as mta_tax,
        tip_amount::double as tip_amount,
        tolls_amount::double as tolls_amount,
        improvement_surcharge::double as improvement_surcharge,
        total_amount::double as total_amount,
        congestion_surcharge::double as congestion_surcharge,
        airport_fee::double as airport_fee,
        cbd_congestion_fee::double as cbd_congestion_fee,
        source_file::varchar as source_file,
        regexp_extract(source_file, 'yellow_tripdata_([0-9]{4}-[0-9]{2})', 1)
            as source_month
    from {{ source("raw", "yellow_trips_raw") }}
),
known_zones as (
    select location_id
    from {{ source("raw", "taxi_zone_lookup") }}
),
with_metrics as (
    select
        *,
        try_strptime(source_month, '%Y-%m')::timestamp as source_month_start,
        cast(pickup_datetime as date) as trip_date,
        date_trunc('hour', pickup_datetime)::timestamp as pickup_local_hour,
        date_diff('second', pickup_datetime, dropoff_datetime) as trip_duration_seconds,
        date_diff('second', pickup_datetime, dropoff_datetime) / 60.0 as trip_duration_min,
        trip_distance
            / nullif(date_diff('second', pickup_datetime, dropoff_datetime) / 3600.0, 0)
            as avg_speed_mph,
        md5(concat_ws(
            '|',
            coalesce(cast(vendor_id as varchar), '<NULL>'),
            coalesce(cast(pickup_datetime as varchar), '<NULL>'),
            coalesce(cast(dropoff_datetime as varchar), '<NULL>'),
            coalesce(cast(passenger_count as varchar), '<NULL>'),
            coalesce(cast(trip_distance as varchar), '<NULL>'),
            coalesce(cast(rate_code_id as varchar), '<NULL>'),
            coalesce(store_and_fwd_flag, '<NULL>'),
            coalesce(cast(pickup_location_id as varchar), '<NULL>'),
            coalesce(cast(dropoff_location_id as varchar), '<NULL>'),
            coalesce(cast(payment_type as varchar), '<NULL>'),
            coalesce(cast(fare_amount as varchar), '<NULL>'),
            coalesce(cast(extra as varchar), '<NULL>'),
            coalesce(cast(mta_tax as varchar), '<NULL>'),
            coalesce(cast(tip_amount as varchar), '<NULL>'),
            coalesce(cast(tolls_amount as varchar), '<NULL>'),
            coalesce(cast(improvement_surcharge as varchar), '<NULL>'),
            coalesce(cast(total_amount as varchar), '<NULL>'),
            coalesce(cast(congestion_surcharge as varchar), '<NULL>'),
            coalesce(cast(airport_fee as varchar), '<NULL>'),
            coalesce(cast(cbd_congestion_fee as varchar), '<NULL>')
        )) as trip_fingerprint
    from raw_trips
),
ranked_trips as (
    select
        *,
        row_number() over (
            partition by trip_fingerprint
            order by source_file
        ) as duplicate_rank
    from with_metrics
),
identified_trips as (
    select
        *,
        md5(concat_ws('|', trip_fingerprint, cast(duplicate_rank as varchar))) as trip_id,
        (
            pickup_location_id in ({{ var("unknown_zone_ids") | join(", ") }})
            or dropoff_location_id in ({{ var("unknown_zone_ids") | join(", ") }})
        ) as is_unknown_zone,
        list_filter(
            [
                case
                    when fare_amount < 0 or total_amount <= 0 then 'NEGATIVE_FARE'
                    else null::varchar
                end,
                case
                    when dropoff_datetime is null
                        or pickup_datetime is null
                        or dropoff_datetime < pickup_datetime
                    then 'DROPOFF_BEFORE_PICKUP'
                    else null::varchar
                end,
                case
                    when trip_duration_seconds < {{ var("zero_duration_seconds") }}
                        and trip_distance > {{ var("zero_duration_distance_threshold") }}
                    then 'ZERO_DURATION'
                    else null::varchar
                end,
                case
                    when trip_duration_min > {{ var("absurd_duration_minutes") }}
                    then 'ABSURD_DURATION'
                    else null::varchar
                end,
                case
                    when trip_distance <= 0
                        and fare_amount > {{ var("zero_distance_fare_threshold") }}
                    then 'ZERO_DISTANCE_PAID'
                    else null::varchar
                end,
                case
                    when trip_distance > {{ var("absurd_distance_miles") }}
                    then 'ABSURD_DISTANCE'
                    else null::varchar
                end,
                case
                    when avg_speed_mph > {{ var("teleporting_speed_mph") }}
                    then 'TELEPORTING_CAB'
                    else null::varchar
                end,
                case
                    when pickup_datetime is null
                        or source_month_start is null
                        or date_trunc('month', pickup_datetime) != source_month_start
                    then 'OUT_OF_RANGE_DATE'
                    else null::varchar
                end,
                case
                    when passenger_count > {{ var("max_passenger_count") }}
                    then 'BAD_PASSENGER_COUNT'
                    else null::varchar
                end,
                case
                    when pickup_location_id is null
                        or dropoff_location_id is null
                        or (
                            pickup_location_id not in ({{ var("unknown_zone_ids") | join(", ") }})
                            and not exists (
                                select 1
                                from known_zones
                                where known_zones.location_id = pickup_location_id
                            )
                        )
                        or (
                            dropoff_location_id not in ({{ var("unknown_zone_ids") | join(", ") }})
                            and not exists (
                                select 1
                                from known_zones
                                where known_zones.location_id = dropoff_location_id
                            )
                        )
                    then 'UNKNOWN_ZONE'
                    else null::varchar
                end,
                case
                    when duplicate_rank > 1 then 'DUPLICATE_TRIP'
                    else null::varchar
                end
            ],
            lambda reason: reason is not null
        ) as reject_reasons
    from ranked_trips
)
select * from identified_trips
