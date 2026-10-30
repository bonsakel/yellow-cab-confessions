select trip_id, reason
from {{ ref("quarantine_trips") }},
    unnest(reject_reasons) as reasons(reason)
where reason not in (
    'NEGATIVE_FARE',
    'DROPOFF_BEFORE_PICKUP',
    'ZERO_DURATION',
    'ABSURD_DURATION',
    'ZERO_DISTANCE_PAID',
    'ABSURD_DISTANCE',
    'TELEPORTING_CAB',
    'OUT_OF_RANGE_DATE',
    'BAD_PASSENGER_COUNT',
    'UNKNOWN_ZONE',
    'DUPLICATE_TRIP'
)
