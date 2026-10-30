with raw_counts as (
    select source_file, count(*) as raw_rows
    from {{ source("raw", "yellow_trips_raw") }}
    group by source_file
),
clean_counts as (
    select source_file, count(*) as clean_rows
    from {{ ref("fct_trips") }}
    group by source_file
),
quarantine_counts as (
    select source_file, count(*) as quarantined_rows
    from {{ ref("quarantine_trips") }}
    group by source_file
)
select
    raw_counts.source_file,
    raw_counts.raw_rows,
    coalesce(clean_counts.clean_rows, 0) as clean_rows,
    coalesce(quarantine_counts.quarantined_rows, 0) as quarantined_rows
from raw_counts
left join clean_counts using (source_file)
left join quarantine_counts using (source_file)
where raw_counts.raw_rows
    != coalesce(clean_counts.clean_rows, 0) + coalesce(quarantine_counts.quarantined_rows, 0)
