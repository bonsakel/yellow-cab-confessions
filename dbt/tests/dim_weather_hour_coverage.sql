with expected as (
    select
        date_diff(
            'day',
            date '{{ var("ycc_year") }}-01-01',
            date '{{ var("ycc_year") + 1 }}-01-01'
        ) * 24 as expected_hours
),
actual as (
    select count(*) as actual_hours
    from {{ ref("dim_weather") }}
)
select actual.actual_hours, expected.expected_hours
from actual
cross join expected
where actual.actual_hours != expected.expected_hours
