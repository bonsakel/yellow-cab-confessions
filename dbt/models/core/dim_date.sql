{{ config(materialized="table") }}

with calendar as (
    select cast(calendar_date as date) as date_day
    from generate_series(
        date '{{ var("ycc_year") }}-01-01',
        date '{{ var("ycc_year") }}-12-31',
        interval 1 day
    ) as dates(calendar_date)
)
select
    cast(strftime(date_day, '%Y%m%d') as integer) as date_key,
    date_day,
    strftime(date_day, '%A') as day_name,
    extract(dow from date_day)::integer as day_of_week,
    extract(week from date_day)::integer as week_of_year,
    extract(month from date_day)::integer as month_number,
    strftime(date_day, '%B') as month_name,
    extract(quarter from date_day)::integer as quarter_number,
    extract(year from date_day)::integer as year_number,
    extract(dow from date_day) in (0, 6) as is_weekend,
    cast(null as varchar) as holiday_name
from calendar
