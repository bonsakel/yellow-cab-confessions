{{ config(materialized="view") }}

select
    try_cast(date as date) as holiday_date,
    holiday_name::varchar as holiday_name
from {{ ref("us_holidays") }}
