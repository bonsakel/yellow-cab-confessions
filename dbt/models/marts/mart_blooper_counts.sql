{{ config(materialized="table") }}

select
    reasons.reason_code,
    trips.source_month,
    count(*) as rejected_trips
from {{ ref("quarantine_trips") }} as trips,
    unnest(trips.reject_reasons) as reasons(reason_code)
group by 1, 2
